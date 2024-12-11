#!/bin/bash

# Stop and remove the existing container
docker stop money-control 2>/dev/null
docker rm money-control 2>/dev/null

# Run the container
docker run --platform=linux/amd64 \
    -p 5173:5173 \
    --name money-control \
    -d money-control