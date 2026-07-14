import oci
import os
import sys

# Écriture temporaire de la clé privée pour l'authentification
private_key_content = os.environ.get("OCI_PRIVATE_KEY")
if not private_key_content:
    print("❌ Erreur: Le secret OCI_PRIVATE_KEY est introuvable sur GitHub.")
    sys.exit(1)

# GitHub Secrets peut parfois altérer les retours à la ligne du PEM
# On s'assure que le format est correct
private_key_content = private_key_content.replace("\\n", "\n").strip()

with open("key.pem", "w") as f:
    f.write(private_key_content)

# Charger la configuration depuis les variables d'environnement (Secrets GitHub)
config = {
    "user": os.environ.get("OCI_USER"),
    "key_file": "key.pem",
    "fingerprint": os.environ.get("OCI_FINGERPRINT"),
    "tenancy": os.environ.get("OCI_TENANCY"),
    "region": os.environ.get("OCI_REGION")
}

print("Vérification de la configuration OCI...")
for key, value in config.items():
    if key == "key_file":
        continue
    if not value:
        print(f"❌ Erreur: Le secret {key.upper()} est vide ou introuvable.")
        sys.exit(1)
    print(f"  ✅ {key} = {value[:20]}...")

try:
    oci.config.validate_config(config)
    print("  ✅ Configuration validée avec succès !")
except oci.exceptions.InvalidConfig as e:
    print(f"❌ Erreur de configuration: {e}")
    sys.exit(1)

compute_client = oci.core.ComputeClient(config)

# La configuration exacte de votre serveur 24Go RAM
instance_details = oci.core.models.LaunchInstanceDetails(
    availability_domain="Ilbo:EU-PARIS-1-AD-1",
    compartment_id="ocid1.tenancy.oc1..aaaaaaaaz4gwhdlkcumvw4lw27vgpwnopicftpferdwf4kyf3nhfjom5efuq",
    display_name="Serveur-n8n-24Go",
    shape="VM.Standard.A1.Flex",
    shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
        ocpus=4,
        memory_in_gbs=24
    ),
    create_vnic_details=oci.core.models.CreateVnicDetails(
        subnet_id="ocid1.subnet.oc1.eu-paris-1.aaaaaaaamuksui4oqp5q4cw7cf7c4prvasg2sq3o7fahq5swspkzkcsxjcca",
        assign_public_ip=True,  # L'IP PUBLIQUE EST ACTIVÉE ICI
        assign_private_dns_record=True
    ),
    source_details=oci.core.models.InstanceSourceViaImageDetails(
        image_id="ocid1.image.oc1.eu-paris-1.aaaaaaaabm4lqa5ok6ciib4ps4sqcujdrxiwpkhdjqdjnbueh3tpupt7tewa"
    ),
    metadata={
        "ssh_authorized_keys": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQDNcdxUMIZUc+vfDIHAfwoJZax6dEZ2mt9BM4mXQ6cP3vD3+F3fkPSrYlX7gPoi+i36ag9COznnWsZR0j+8uz5nLwlhEWZ+sk69WvZam4jgPTFhlD0odJET8UViqfIOuAeQgN1B4/JCRjFAff54nJjwcxz5tOA6P3G0Iw5Ne0nynxhqEG94/0oGk4x9Zo1YwpUGWWcEQtEAseBgIeGC55ur92MWUo3EAonvQf9SK3IvIpnKmFqV2whJMV0iage/Hwu9X7I+z/L4dPTcbMwjeNod6aWyTmxq3qnHSGXRlVNies3ZhotNyWw5OLunPrKbIkf3rSh+9pt6DKQTZEVm6zTV ssh-key-2026-07-14"
    }
)

print("\n🔄 Tentative de création du serveur Ampere 24Go...")
try:
    response = compute_client.launch_instance(instance_details)
    print("=====================================================")
    print("🚀 SUCCÈS ! LE SERVEUR A ÉTÉ CRÉÉ AVEC SUCCÈS !")
    print(f"   ID: {response.data.id}")
    print(f"   État: {response.data.lifecycle_state}")
    print("   Allez vite sur le site d'Oracle pour voir votre serveur.")
    print("=====================================================")
    sys.exit(0)  # Succès ! Le workflow ne se relancera plus en boucle
except oci.exceptions.ServiceError as e:
    if e.status == 500 and "Out of host capacity" in e.message:
        print("❌ Plus de place chez Oracle (Out of capacity). Le robot réessaiera dans 5 minutes.")
        sys.exit(1)
    elif e.status == 400 and "LimitExceeded" in str(e.code):
        print("⚠️ Limite atteinte : le serveur existe peut-être déjà ! Vérifiez sur Oracle Cloud.")
        sys.exit(0)
    else:
        print(f"❌ Erreur inattendue de l'API Oracle (code {e.status}): {e.message}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Erreur Python inattendue: {type(e).__name__}: {e}")
    sys.exit(1)
