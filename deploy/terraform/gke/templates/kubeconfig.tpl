apiVersion: v1
kind: Config
current-context: fred-sa@${vars.cluster_name}
preferences: {}
clusters:
- cluster:
    certificate-authority-data: ${vars.cluster_ca_certificate}
    server: ${vars.cluster_server}
  name: ${vars.cluster_name}
contexts:
- context:
    cluster: ${vars.cluster_name}
    user: fred-sa
  name: fred-sa@${vars.cluster_name}
users:
- name: fred-sa
  user:
    token: ${vars.user_access_token}