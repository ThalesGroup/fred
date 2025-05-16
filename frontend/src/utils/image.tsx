import { Box, Typography, useTheme } from '@mui/material';
import { useEffect, useState } from 'react';
interface ImageProps {
  name: string;
  width?: string;
  height?: string;
  showLabel?: boolean;
}

// Functional component to return the image
// It takes the name of the image, width, and height as props and will lokk for an image 
// in the public/images folder with the name provided. If the image is not found, it will
// fallback to a default image.
export const ImageComponent = ({ name, width, height }: ImageProps) => {
  const [imageSrc, setImageSrc] = useState(`/images/${name}.svg`);
  const [imageExists, setImageExists] = useState(true);
  const imageStyle = { width, height };

  useEffect(() => {
    const img = new Image();
    img.src = `/images/${name}.svg`;
    img.onload = () => {
      setImageExists(true);  // If the image loads successfully
      setImageSrc(`/images/${name}.svg`);
    };

    img.onerror = () => {
      console.log("image not found", name)
      setImageExists(false);  // If the image doesn't exist, use fallback
      setImageSrc(`/images/package-thin-svgrepo-com.svg`);
    };
  }, [name]);
  return (
    <div>
      <img src={imageSrc} alt={imageExists ? name : 'default'} style={imageStyle} />
    </div>
  );
};

// Utility function to get logo for resource kind
export const KindLogoComponent = ({ name, width = '50px', height = '50px' }: ImageProps) => {
  switch (name.toLowerCase()) {
    case "deployment":
      return <LogoComponent name={'k8/resources/unlabeled/deploy'} width={width} height={height} />;
    case "statefulset":
      return <LogoComponent name={'k8/resources/unlabeled/sts'} width={width} height={height} />;
    case "daemonset":
      return <LogoComponent name={'k8/resources/unlabeled/ds'} width={width} height={height} />;
    default:
      return <LogoComponent name={name} width={width} height={height} />;  // Fallback to generic logo
  }
};
const iconMap: Record<string, string> = {
  minio: 'icons/minio',
  mysql: 'icons/mysql',
  coredns: 'icons/coredns',
  nginx: 'icons/nginx',
  postgres: 'icons/postgres',
  redis: 'icons/redis',
  cassandra: 'icons/cassandra',
  kafka: 'icons/kafka',
  etcd: 'icons/etcd',
  prometheus: 'icons/prometheus',
  grafana: 'icons/grafana',
  helm: 'icons/helm',
  istio: 'icons/istio',
  linkerd: 'icons/linkerd',
  contour: 'icons/contour',
  traefik: 'icons/traefik',
  envoy: 'icons/envoy',
  kubernetes: 'icons/kubernetes',
  harbor: 'icons/harbor',
  flux: 'icons/flux',
  argo: 'icons/argo',
  rook: 'icons/rook',
  openebs: 'icons/openebs',
  opensearch: 'icons/opensearch',
  opentelemetry: 'icons/opentelemetry',
  fluentd: 'icons/fluentd',
  jaeger: 'icons/jaeger',
  cert_manager: 'icons/cert-manager',
  spinnaker: 'icons/spinnaker',
  elasticsearch: 'icons/elasticsearch',
  loki: 'icons/loki',
  tempo: 'icons/tempo',
  vault: 'icons/vault',
  metallb: 'icons/metallb',
  kubevirt: 'icons/kubevirt',
  calico: 'icons/calico',
  tigera: 'icons/tigera',
  knative: 'icons/knative',
  rabbitmq: 'icons/rabbitmq',
  thanos: 'icons/thanos',
  dragonfly: 'icons/dragonfly',
  // Add more mappings here as needed
};

export const IconComponent = ({ name = '', width = '50px', height = '50px' }: ImageProps) => {
  // Find the first matching icon name based on the provided name
  const matchedIcon = Object.keys(iconMap).find((key) => name.includes(key));
  if (!matchedIcon) {
    console.warn("unmatched icon", name);
  } 
  // Use the matched icon path, or fallback to 'unknown' if none matches
  const iconPath = matchedIcon ? iconMap[matchedIcon] : 'unknown';
  return <LogoComponent name={iconPath} width={width} height={height} />;
};

export const LogoComponent = ({ name = '', width = '50px', height = '50px', showLabel = false }: ImageProps) => {
  const [imageSrc, setImageSrc] = useState(`/images/${name}.svg`);
  const [imageExists, setImageExists] = useState(true);

  const theme = useTheme();
  const imageStyle: React.CSSProperties = { width, height, objectFit: 'contain' };

  useEffect(() => {
    const img = new Image();
    img.src = `/images/${name}.svg`;
    img.onload = () => {
      setImageExists(true);  // Image loaded successfully
      setImageSrc(`/images/${name}.svg`);
    };

    img.onerror = () => {
      console.warn("logo not found", name);
      setImageExists(false);  // Fallback to default image
      setImageSrc(`/images/package-thin-svgrepo-com.svg`);
    };
  }, [name]);

  // Define a chip-style box with padding, border, and adaptive background
  return (
    <Box
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '8px',
        borderRadius: '8px',
        backgroundColor: theme.palette.mode === 'dark' ? theme.palette.primary.light : '#e0e0e0',  // Adaptive background color
        border: `1px solid ${theme.palette.mode === 'dark' ? '#fff' : '#000'}`,  // Adaptive border color
      }}
    >
      {/* Image */}
      <img src={imageSrc} alt={imageExists ? name : 'default'} style={imageStyle} />

      {/* Conditionally show the label only if showLabel is true */}
      {showLabel && !imageExists && (
        <Typography
          variant="caption"
          sx={{ marginLeft: 1, color: theme.palette.text.primary }}
        >
          {name}
        </Typography>
      )}
    </Box>
  );
};