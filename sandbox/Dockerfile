# Imagen mínima donde se ejecutan las pruebas del código de los estudiantes (SANDBOX_MODE=docker).
# Se ejecuta con --network none, --read-only, --cap-drop ALL y usuario nobody.
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest numpy pandas scikit-learn matplotlib requests pydantic
WORKDIR /work
