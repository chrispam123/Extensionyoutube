#!/bin/bash
# -*- coding: utf-8 -*-
# Purpose: CONSTRUYE LAS LAMBDAS EN LOCAL .zip PARA PROBAR EL CODIGO EN LOCALSTACK Y AWS SIMULADOS

set -e # Falla rápido si algo sale mal

echo "🧹 Limpiando artefactos anteriores..."
rm -rf dist/
mkdir -p dist/worker
mkdir -p dist/dispatcher

echo "📦 Construyendo WORKER..."
# Exportamos dependencias de Poetry
poetry export -f requirements.txt --output dist/worker/requirements.txt
# Instalamos librerías (ignorando las del sistema)
pip install -r dist/worker/requirements.txt -t dist/worker/ --ignore-installed --quiet
# Copiamos código y capa shared
cp src/worker/handler.py dist/worker/
cp -r src/shared dist/worker/
# Zipeamos el contenido (no la carpeta)
cd dist/worker && zip -r ../worker.zip . > /dev/null && cd ../..

echo "📦 Construyendo DISPATCHER..."
# El dispatcher es ligero, solo instalamos powertools y httpx (si lo necesitara)
# Añadimos aws-xray-sdk porque Powertools lo necesita para el Tracer
# Usamos el mismo requirements que el Worker para asegurar paridad de versiones
# (Aunque sea un poco más pesado, ganamos en SEGURIDAD y DETERMINISMO)
pip install -r dist/worker/requirements.txt -t dist/dispatcher/ --ignore-installed --quiet
cp src/dispatcher/dispatcher.py dist/dispatcher/
cp -r src/shared dist/dispatcher/
cd dist/dispatcher && zip -r ../dispatcher.zip . > /dev/null && cd ../..

echo "✅ Artefactos listos en la carpeta dist/"
