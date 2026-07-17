import oci
import os
import sys

# ──────────────────────────────────────────────────────────────
# 1. Récupération et nettoyage de la clé privée OCI
# ──────────────────────────────────────────────────────────────
private_key_content = os.environ.get("OCI_PRIVATE_KEY", "")

if not private_key_content:
    print("❌ Erreur: Le secret OCI_PRIVATE_KEY est introuvable sur GitHub.")
    sys.exit(1)

# GitHub Secrets peut encoder les retours à la ligne comme des \n littéraux
# On les transforme en vrais sauts de ligne si nécessaire
if "\\n" in private_key_content:
    private_key_content = private_key_content.replace("\\n", "\n")

# Nettoyer les espaces en début/fin de chaque ligne (mais garder les \n)
lines = private_key_content.strip().splitlines()
private_key_content = "\n".join(line.strip() for line in lines) + "\n"

# Validation basique du format PEM
if "-----BEGIN" not in private_key_content or "-----END" not in private_key_content:
    print("❌ Erreur: La clé privée n'a pas un format PEM valide.")
    print(f"   Début de la clé: {private_key_content[:40]}...")
    sys.exit(1)

print("🔑 Clé privée PEM chargée avec succès.")
print(f"   Format: {'PKCS#8' if 'BEGIN PRIVATE KEY' in private_key_content else 'PKCS#1 RSA'}")
print(f"   Longueur: {len(private_key_content)} caractères")
print(f"   Dernière ligne: ...{private_key_content.strip().splitlines()[-1]}")

# ──────────────────────────────────────────────────────────────
# 2. Configuration OCI (utilise key_content au lieu de key_file)
# ──────────────────────────────────────────────────────────────
config = {
    "user": os.environ.get("OCI_USER", "").strip(),
    "key_content": private_key_content,
    "fingerprint": os.environ.get("OCI_FINGERPRINT", "").strip(),
    "tenancy": os.environ.get("OCI_TENANCY", "").strip(),
    "region": os.environ.get("OCI_REGION", "").strip(),
}

print("\nVérification de la configuration OCI...")
for key, value in config.items():
    if key == "key_content":
        continue
    if not value:
        print(f"  ❌ {key.upper()} est vide ou introuvable !")
        sys.exit(1)
    # Masquer partiellement les valeurs sensibles
    display = value[:25] + "..." if len(value) > 25 else value
    print(f"  ✅ {key} = {display}")

try:
    oci.config.validate_config(config)
    print("  ✅ Configuration validée avec succès !")
except oci.exceptions.InvalidConfig as e:
    print(f"  ❌ Erreur de configuration: {e}")
    sys.exit(1)

# ──────────────────────────────────────────────────────────────
# 3. Création du client et lancement de l'instance
# ──────────────────────────────────────────────────────────────
compute_client = oci.core.ComputeClient(config)

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
        assign_public_ip=True,
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
    print("   Allez vite sur Oracle Cloud pour voir votre serveur.")
    print("=====================================================")
    sys.exit(0)
except oci.exceptions.ServiceError as e:
    if e.status == 500 and "Out of host capacity" in e.message:
        print("❌ Out of capacity. Le robot réessaiera dans 5 minutes.")
        sys.exit(1)
    elif e.status == 400 and "LimitExceeded" in str(e.code):
        print("⚠️ Limite atteinte : le serveur existe peut-être déjà !")
        sys.exit(0)
    elif e.status == 401:
        print(f"❌ ERREUR 401 - Authentification refusée: {e.message}")
        print("   Causes possibles:")
        print("   - La clé privée ne correspond pas au fingerprint sur Oracle")
        print("   - La clé API a été supprimée ou régénérée sur Oracle")
        print("   - L'OCI_USER ou OCI_FINGERPRINT est incorrect")
        sys.exit(1)
    else:
        print(f"❌ Erreur API Oracle (code {e.status}): {e.message}")
        sys.exit(1)
except Exception as e:
    print(f"❌ Erreur Python inattendue: {type(e).__name__}: {e}")
    sys.exit(1)
