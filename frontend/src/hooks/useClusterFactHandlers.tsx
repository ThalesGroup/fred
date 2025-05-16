import { useState, useEffect } from 'react';
import { FactList, Fact, createFactList } from '../slices/factsStructures.tsx';
import { useToast } from "../components/ToastProvider.tsx";
import { useConfirmationDialog } from '../components/ConfirmationDialogProvider.tsx';
import { useGetClusterFactsMutation, usePostClusterFactsMutation, useDeleteClusterFactsMutation } from '../slices/api.tsx';

interface UseFactHandlersProps {
  cluster: string;
}

export const useClusterFactHandlers = ({ cluster }: UseFactHandlersProps) => {
  const [factList, setFactList] = useState<FactList>(createFactList());
  const [getClusterFacts] = useGetClusterFactsMutation();
  const [postClusterFacts] = usePostClusterFactsMutation();
  const [deleteClusterFacts] = useDeleteClusterFactsMutation();  
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  // Fetch initial fact list
  useEffect(() => {
    if (cluster) {
      getClusterFacts({
        cluster,
      })
        .unwrap()
        .then(setFactList)
        .catch((error) => {
          console.error(error);
          showError({ summary: 'Error', detail: 'Failed to fetch facts.' });
        });
    }
  }, [cluster]);

  const handleSubmit = async (newFact: Fact) => {
    try {
      const updatedFactList = {
        ...factList,
        facts: [...factList.facts, newFact],
      };
      setFactList(updatedFactList);

      await postClusterFacts({
        cluster,
        fact: newFact,
      }).unwrap();

      showSuccess({ summary: 'Success', detail: 'Fact added successfully.' });
    } catch (error) {
      showError({ summary: 'Error', detail: 'Failed to add fact.' });
    }
  };

  const handleEdit = async (title: string, newContent: string) => {
    try {
      setFactList(prevFactList => ({
        ...prevFactList,
        facts: prevFactList.facts.map(fact =>
          fact.title === title ? { ...fact, content: newContent } : fact
        ),
      }));

      const factToUpdate = factList.facts.find(fact => fact.title === title);
      if (factToUpdate) {
        await postClusterFacts({
          cluster,
          fact: { ...factToUpdate, content: newContent },
        }).unwrap();
      }

      showSuccess({ summary: 'Success', detail: 'Fact updated successfully.' });
    } catch (error) {
      showError({ summary: 'Error', detail: 'Failed to update fact.' });
    }
  };

  const handleDelete = async (title: string) => {
    showConfirmationDialog({
      title: "Delete Fact",
      message: `Are you sure you want to delete the ${title} fact?`,
      onConfirm: async () => {
        try {
          const factToDelete = factList.facts.find(fact => fact.title === title);
          if (factToDelete) {
            await deleteClusterFacts({
              cluster,
              fact: factToDelete,
            }).unwrap();

            setFactList(prevFactList => ({
              ...prevFactList,
              facts: prevFactList.facts.filter(fact => fact.title !== title),
            }));

            showSuccess({ summary: 'Success', detail: 'Fact deleted successfully.' });
          }
        } catch (error) {
          showError({ summary: 'Error', detail: 'Failed to delete fact.' });
        }
      },
    });
  };

  return {
    factList,
    setFactList,
    handleSubmit,
    handleEdit,
    handleDelete,
  };
};
