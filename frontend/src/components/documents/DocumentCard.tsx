// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Card, CardContent, Typography, IconButton, Box, Tooltip, Collapse, darken, useTheme } from "@mui/material";
import Delete from "@mui/icons-material/Delete";
import EventAvailableIcon from "@mui/icons-material/EventAvailable";
import { useEffect, useState } from "react";
import { useGetDocumentMetadataMutation, usePutDocumentMetadataMutation } from "../../slices/documentApi";
import { WordIcon, PdfIcon, ExcelIcon } from '../../utils/icons';
import { IOSSwitch } from "../../utils/iosSwitch";
import dayjs from 'dayjs'; // Import dayjs for date formatting
import { getAgentBadge } from "../../utils/avatar";

export interface Metadata {
  metadata: any;
}

export const DocumentCard = ({ fileName, onDelete, size, fileId, retrievable, date_added_to_kb, agent_name, isAdmin }) => {
  // Déclare un état pour la taille de la police, initialisé à '1rem'
  const [, setFontSize] = useState('1rem');

  // Ajuste le nom du fichier
  const adjustedFileName = fileName;

  // Extrait et met en majuscule l'extension du fichier
  const fileExtension = fileName.split('.').pop().toUpperCase();

  // Déclare une mutation pour récupérer les métadonnées du document
  const [retrieveMetadata] = useGetDocumentMetadataMutation();

  // Déclare un état pour stocker les métadonnées, initialisé à null
  const [metadata, setMetadata] = useState<Metadata | null>();

  // Déclare un état pour afficher ou masquer les métadonnées
  const [displayMetadata, setDisplayMetaData] = useState(false);

  // Déclare une mutation pour mettre à jour les métadonnées du document
  const [updateMetadata] = usePutDocumentMetadataMutation();

  // Déclare un état pour indiquer si les métadonnées doivent être récupérées, initialisé à true
  const [, setShouldRetrieveMetadata] = useState(true);

  // Déclare un état pour indiquer si le document est récupérable, initialisé avec la valeur de la prop 'retrievable'
  const [isRetrievable, setIsRetrievable] = useState(retrievable);

  // Utilise le thème de l'application
  const theme = useTheme();

  // Utilise un effet pour ajuster la taille de la police en fonction de la taille du conteneur
  useEffect(() => {
    const adjustFontSize = () => {
      const container = document.getElementById('document-name');
      if (container) {
        let newFontSize = 1;
        container.style.fontSize = `${newFontSize}rem`;

        // Réduit la taille de la police jusqu'à ce que le texte tienne dans le conteneur
        while (container.scrollHeight > container.clientHeight && newFontSize > 0.5) {
          newFontSize -= 0.1;
          container.style.fontSize = `${newFontSize}rem`;
        }

        setFontSize(`${newFontSize}rem`);
      }
    };

    adjustFontSize();
    window.addEventListener('resize', adjustFontSize);

    // Nettoie l'effet en supprimant l'écouteur d'événements lors du démontage du composant
    return () => {
      window.removeEventListener('resize', adjustFontSize);
    };
  }, [adjustedFileName]);

  // Fonction pour afficher ou masquer les métadonnées
  const handleDisplayMetadata = async () => {
    try {
      const response = await retrieveMetadata({ document_uid: fileId }).unwrap();
      setMetadata(response);
      setShouldRetrieveMetadata(false); // Réinitialise l'état après récupération
      setDisplayMetaData(!displayMetadata);
    } catch (error) {
      console.log(error);
    }
  };

  // Fonction pour basculer l'état de récupérabilité du document
  const handleToggleRetrievable = async (event) => {
    event.stopPropagation(); // Arrête la propagation de l'événement de clic
    try {
      const updatedMetadata = {
        ...metadata,
        retrievable: !isRetrievable,
      };

      await updateMetadata({ document_uid: fileId, metadata: updatedMetadata }).unwrap();
      setIsRetrievable(!isRetrievable);
      setShouldRetrieveMetadata(true); // Déclenche la récupération des métadonnées

      // Relance la requête pour récupérer les métadonnées mises à jour
      const response = await retrieveMetadata({ document_uid: fileId }).unwrap();
      setMetadata(response);
    } catch (error) {
      console.error('Error updating files:', error);
    }
  };

  // Fonction pour formater une date en 'DD/MM/YYYY'
  const formatDate = (dateString) => {
    return dayjs(dateString).format('DD/MM/YYYY');
  };
 
  return (
    <Card
      elevation={1}
      sx={{
        padding: size === "small" ? "8px" : "10px",
        marginBottom: "12px", // Ajout d'un espace en bas pour séparer les cartes
        borderRadius: "10px",
        zIndex: 3,
        position: "relative",
        width: size === 'small' ? "350px" : "100%",
        height: displayMetadata ? "auto" : "56px",
        maxHeight: '280px',
        transition: "all 0.2s ease-in-out",
        '&:hover': {
          backgroundColor: (theme) => darken(theme.palette.background.default, 0.08),
        },
        alignContent: 'center',
        justifyContent: 'center',
        backgroundColor: theme.palette.background.paper,
      }}
      onClick={() => size !== 'small' ? handleDisplayMetadata() : null}
    >
      <Box display="flex" flexDirection="row" alignItems="center" width="100%">
        {fileExtension === 'DOCX' ? (
          <WordIcon style={{ width: '30px', height: '30px' }} />
        ) : fileExtension === 'PDF' ? (
          <PdfIcon style={{ width: '20px', height: '20px' }} />
        ) : fileExtension === 'XLSX' ? (
          <ExcelIcon style={{ width: '20px', height: '20px' }} />
        ) : (
          <Typography
            variant="caption"
            sx={{
              backgroundColor: theme.palette.primary.main,
              color: theme.palette.primary.contrastText,
              padding: '2px 5px',
              borderRadius: '3px',
            }}
          >
            {fileExtension}
          </Typography>
        )}
        <Typography
          id="document-name"
          variant="h6"
          sx={{
            marginLeft: size === 'small' ? '12px' : '30px', // Increased spacing
            flex: 1,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            fontSize: size === 'small' ? '14px' : '16px',
            maxWidth: "860px",
            marginRight: '20px',
            minWidth: "20%"
          }}
        >
          {adjustedFileName}
        </Typography>

        {agent_name && (
          <Box sx={{ marginRight: '10%' }}>
            {getAgentBadge(agent_name)}
          </Box>
        )}

        {date_added_to_kb && (
          <Tooltip title="Date d'ajout à la base documentaire">
            <Box
              display="flex"
              alignItems="center"
              sx={{
                backgroundColor: theme.palette.mode === 'dark' ? theme.palette.text.disabled : theme.palette.chip.mediumGrey,
                borderRadius: '15px',
                padding: '5px',
                fontSize: '0.75rem',
                height: '24px'
              }}
            >
              <EventAvailableIcon sx={{ fontSize: '20px', mr: 0.5, color: theme.palette.text.secondary, marginLeft: '5px' }} />
              <Typography
                variant="body1"
                sx={{
                  marginLeft: '10px',
                  marginRight: '10px',
                  whiteSpace: 'nowrap',
                }}
              >
                {formatDate(date_added_to_kb)}
              </Typography>
            </Box>
          </Tooltip>
        )}
        {size !== 'small' && (
          <Box sx={{ marginLeft: 6, marginRight: '40px' }}> {/* Adjusted position */}
            <Tooltip enterDelay={500} title={isRetrievable ? "The document is retrievable" : "The document is not retrieable"}>
              <Box onClick={(event) => event.stopPropagation()}>
                <IOSSwitch
                  checked={isRetrievable}
                  onChange={isAdmin ? handleToggleRetrievable : null}
                  sx={{ zIndex: 5 }}
                />
              </Box>
            </Tooltip>
          </Box>
        )}
        {
          isAdmin && (<IconButton
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
            onMouseDown={(event) => event.stopPropagation()}
            sx={{ width: '15px', height: '15px', marginRight: '12px' }}
          >
            <Delete />
          </IconButton>)
        }

      </Box>
      <Collapse in={(displayMetadata && metadata != undefined)} timeout="auto" unmountOnExit>
        <CardContent sx={{ width: '100%', paddingTop: '10px' }}>
          {Object.entries(metadata?.metadata ?? {}).map(([key, value]) => (
            <Box key={key} sx={{ display: 'flex', flexDirection: 'row' }}>
              <Typography variant="body2">
                <strong>{key}:</strong>
              </Typography>
              <Typography variant="body2" sx={{ marginLeft: '5px' }}>
                {String(value)}
              </Typography>
            </Box>
          ))}
        </CardContent>
      </Collapse>
    </Card>
  );
};