# Kpack deployment

## kpack-dev quick start

You need to have a local kubernetes cluster up and running, either minikube or k3d.

Initialize the kast token
```sh
kastctl pass --init --token <KAST_TOKEN>
```

Launch the installation
```sh
kastctl install --kpack kpack-dev.yml --deployment-path . --token <KAST_TOKEN>
```

Configure your /etc/hosts
```sh
grep -q "127.0.0.1.*auth.dev.local" /etc/hosts || { echo "127.0.0.1 auth.dev.local" | sudo tee -a /etc/hosts ; }
grep -q "127.0.0.1.*minio.dev.local" /etc/hosts || { echo "127.0.0.1 minio.dev.local" | sudo tee -a /etc/hosts ; }
grep -q "127.0.0.1.*opensearch.dev.local" /etc/hosts || { echo "127.0.0.1 opensearch.dev.local" | sudo tee -a /etc/hosts ; }
grep -q "127.0.0.1.*www.dev.local" /etc/hosts || { echo "127.0.0.1 www.dev.local" | sudo tee -a /etc/hosts ; }
grep -q "127.0.0.1.*api.dev.local" /etc/hosts || { echo "127.0.0.1 api.dev.local" | sudo tee -a /etc/hosts ; }
```

Get the users password
```sh
kastctl pass --show --token <KAST_TOKEN>
```

Access

- Keycloak: https://auth.dev.local
- Minio: https://minio.dev.local
- Opensearch: https://opensearch.dev.local
- Fred ui: https://www.dev.local
- Fred API: https://api.dev.local
