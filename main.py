import oci
import os
import sys
import time

# ──────────────────────────────────────────────────────────────
# 1. Récupération et nettoyage de la clé privée OCI
# ──────────────────────────────────────────────────────────────
private_key_content = os.environ.get("OCI_PRIVATE_KEY", "")
if not private_key_content:
    print("❌ Erreur: Le secret OCI_PRIVATE_KEY est introuvable.")
    sys.exit(1)

if "\\n" in private_key_content:
    private_key_content = private_key_content.replace("\\n", "\n")
lines = private_key_content.strip().splitlines()
private_key_content = "\n".join(line.strip() for line in lines) + "\n"

if "-----BEGIN" not in private_key_content:
    print("❌ La clé privée n'a pas un format PEM valide.")
    sys.exit(1)

print("🔑 Clé privée PEM chargée avec succès.")

# ──────────────────────────────────────────────────────────────
# 2. Configuration OCI
# ──────────────────────────────────────────────────────────────
COMPARTMENT_ID = "ocid1.tenancy.oc1..aaaaaaaaz4gwhdlkcumvw4lw27vgpwnopicftpferdwf4kyf3nhfjom5efuq"
AD_NAME = "Ilbo:EU-PARIS-1-AD-1"
IMAGE_ID = "ocid1.image.oc1.eu-paris-1.aaaaaaaabm4lqa5ok6ciib4ps4sqcujdrxiwpkhdjqdjnbueh3tpupt7tewa"
SSH_KEY = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDNcdxUMIZUc+vfDIHAfwoJZax6dEZ2mt9BM4mXQ6cP3vD3+F3fkPSrYlX7gPoi+i36ag9COznnWsZR0j+8uz5nLwlhEWZ+sk69WvZam4jgPTFhlD0odJET8UViqfIOuAeQgN1B4/JCRjFAff54nJjwcxz5tOA6P3G0Iw5Ne0nynxhqEG94/0oGk4x9Zo1YwpUGWWcEQtEAseBgIeGC55ur92MWUo3EAonvQf9SK3IvIpnKmFqV2whJMV0iage/Hwu9X7I+z/L4dPTcbMwjeNod6aWyTmxq3qnHSGXRlVNies3ZhotNyWw5OLunPrKbIkf3rSh+9pt6DKQTZEVm6zTV ssh-key-2026-07-14"

config = {
    "user": os.environ.get("OCI_USER", "").strip(),
    "key_content": private_key_content,
    "fingerprint": os.environ.get("OCI_FINGERPRINT", "").strip(),
    "tenancy": os.environ.get("OCI_TENANCY", "").strip(),
    "region": os.environ.get("OCI_REGION", "").strip(),
}

print("Vérification de la configuration OCI...")
for key, value in config.items():
    if key == "key_content":
        continue
    if not value:
        print(f"  ❌ {key.upper()} est vide !")
        sys.exit(1)
    print(f"  ✅ {key} = {value[:25]}...")

try:
    oci.config.validate_config(config)
    print("  ✅ Configuration validée !")
except oci.exceptions.InvalidConfig as e:
    print(f"  ❌ Configuration invalide: {e}")
    sys.exit(1)

compute_client = oci.core.ComputeClient(config)
network_client = oci.core.VirtualNetworkClient(config)

# ──────────────────────────────────────────────────────────────
# 3. Trouver ou créer le réseau (VCN + Subnet + Internet Gateway)
# ──────────────────────────────────────────────────────────────
def find_or_create_network():
    """Trouve un subnet public existant ou en crée un nouveau."""
    
    # Chercher un VCN existant nommé "vcn-n8n-bot"
    print("\n🌐 Recherche du réseau...")
    vcns = network_client.list_vcns(COMPARTMENT_ID).data
    vcn = None
    for v in vcns:
        if v.lifecycle_state == "AVAILABLE":
            vcn = v
            print(f"  ✅ VCN trouvé: {v.display_name} ({v.id[:40]}...)")
            break

    if not vcn:
        print("  📦 Aucun VCN trouvé. Création d'un nouveau réseau...")
        vcn_response = network_client.create_vcn(
            oci.core.models.CreateVcnDetails(
                compartment_id=COMPARTMENT_ID,
                display_name="vcn-n8n-bot",
                cidr_blocks=["10.0.0.0/16"]
            )
        )
        vcn = vcn_response.data
        # Attendre que le VCN soit prêt
        time.sleep(5)
        print(f"  ✅ VCN créé: {vcn.display_name}")

    # Chercher ou créer un Internet Gateway
    igs = network_client.list_internet_gateways(COMPARTMENT_ID, vcn_id=vcn.id).data
    ig = None
    for g in igs:
        if g.lifecycle_state == "AVAILABLE":
            ig = g
            print(f"  ✅ Internet Gateway trouvé: {g.display_name}")
            break

    if not ig:
        print("  📦 Création de l'Internet Gateway...")
        ig_response = network_client.create_internet_gateway(
            oci.core.models.CreateInternetGatewayDetails(
                compartment_id=COMPARTMENT_ID,
                vcn_id=vcn.id,
                display_name="ig-n8n-bot",
                is_enabled=True
            )
        )
        ig = ig_response.data
        time.sleep(3)
        print(f"  ✅ Internet Gateway créé")

    # Mettre à jour la route table par défaut pour utiliser l'Internet Gateway
    rt_id = vcn.default_route_table_id
    try:
        network_client.update_route_table(
            rt_id,
            oci.core.models.UpdateRouteTableDetails(
                route_rules=[
                    oci.core.models.RouteRule(
                        destination="0.0.0.0/0",
                        destination_type="CIDR_BLOCK",
                        network_entity_id=ig.id
                    )
                ]
            )
        )
        print("  ✅ Route table configurée (accès internet)")
    except Exception as e:
        print(f"  ⚠️ Route table déjà configurée ou erreur mineure: {e}")

    # Chercher un subnet public existant
    subnets = network_client.list_subnets(COMPARTMENT_ID, vcn_id=vcn.id).data
    subnet = None
    for s in subnets:
        if s.lifecycle_state == "AVAILABLE":
            subnet = s
            print(f"  ✅ Subnet trouvé: {s.display_name} ({s.id[:40]}...)")
            break

    if not subnet:
        print("  📦 Création du subnet public...")
        subnet_response = network_client.create_subnet(
            oci.core.models.CreateSubnetDetails(
                compartment_id=COMPARTMENT_ID,
                vcn_id=vcn.id,
                display_name="subnet-n8n-bot",
                cidr_block="10.0.0.0/24",
                route_table_id=rt_id,
                security_list_ids=[vcn.default_security_list_id]
            )
        )
        subnet = subnet_response.data
        time.sleep(5)
        print(f"  ✅ Subnet créé: {subnet.display_name}")

    return subnet.id

# ──────────────────────────────────────────────────────────────
# 4. Lancement de l'instance
# ──────────────────────────────────────────────────────────────
try:
    subnet_id = find_or_create_network()
except Exception as e:
    print(f"❌ Erreur réseau: {type(e).__name__}: {e}")
    sys.exit(1)

instance_details = oci.core.models.LaunchInstanceDetails(
    availability_domain=AD_NAME,
    compartment_id=COMPARTMENT_ID,
    display_name="Serveur-n8n-24Go",
    shape="VM.Standard.A1.Flex",
    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=4,
        memory_in_gbs=24
    ),
    create_vnic_details=oci.core.models.CreateVnicDetails(
        subnet_id=subnet_id,
        assign_public_ip=True,
        assign_private_dns_record=True
    ),
    source_details=oci.core.models.InstanceSourceViaImageDetails(
        image_id=IMAGE_ID
    ),
    metadata={
        "ssh_authorized_keys": SSH_KEY
    }
)

print("\n🔄 Tentative de création du serveur Ampere 24Go...")
try:
    response = compute_client.launch_instance(instance_details)
    print("=====================================================")
    print("🚀 SUCCÈS ! LE SERVEUR A ÉTÉ CRÉÉ !")
    print(f"   ID: {response.data.id}")
    print(f"   État: {response.data.lifecycle_state}")
    print("   Allez sur Oracle Cloud pour voir votre serveur.")
    print("=====================================================")
    sys.exit(0)
except oci.exceptions.ServiceError as e:
    if e.status == 500 and "Out of host capacity" in e.message:
        print("❌ Out of capacity. Prochaine tentative dans 5 min.")
        sys.exit(1)
    elif e.status == 400 and "LimitExceeded" in str(e.code):
        print("⚠️ Limite atteinte : le serveur existe peut-être déjà !")
        sys.exit(0)
    else:
        print(f"❌ Erreur API Oracle (code {e.status}): {e.message}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Erreur Python: {type(e).__name__}: {e}")
    sys.exit(1)
