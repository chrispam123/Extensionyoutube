# Ahora vamos a crear el archivo que conecta Terraform con tu bucket real de AWS. Este archivo vivirá
#dentro de infra/environments/local/..Principio Fundamental: El Backend es el "Ancla".
# El bloque backend es lo primero que Terraform lee. Es lo que le permite saber qué construyó la última vez.
# Aunque estemos trabajando con LocalStack para los recursos (SQS, Dynamo), el Estado lo guardaremos en AWS Real para que aprendas cómo se gestiona en producción.



terraform {
  backend "s3" {
    bucket = "extension-terraform-state-youtube"
    key    = "local/terraform.tfstate" # Ruta dentro del bucket
    region = "us-east-1"

    # ACTIVACIÓN DEL BLOQUEO NATIVO (v1.10+)
    # Al no especificar 'dynamodb_table', Terraform 1.10+
    # usará automáticamente las capacidades de S3 Object Lock.
    use_lockfile = true
  }
}
