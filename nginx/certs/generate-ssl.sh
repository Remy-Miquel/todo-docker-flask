 #!/bin/bash

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout key.pem \
    -out cert.pem \
    -subj "/C=FR/ST=Local/L=Local/O=TodoApp/CN=localhost"

echo "Certificats générés : cert.pem et key.pem"
