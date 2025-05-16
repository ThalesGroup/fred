import { useState, useEffect } from 'react';
import { useDeleteWorkloadFactsMutation, usePostWorkloadFactsMutation, useGetWorkloadFactsMutation } from "../slices/api.tsx";
import { FactList, Fact, createFactList } from '../slices/factsStructures.tsx';
import { useToast } from "../components/ToastProvider.tsx";
import { useConfirmationDialog } from '../components/ConfirmationDialogProvider.tsx';

interface UseFactHandlersProps {
  cluster: string;
  namespace: string;
  workload: string;
  kind: string;
}

export const useWorkloadFactHandlers = ({ cluster, namespace, workload, kind }: UseFactHandlersProps) => {
  const [factList, setFactList] = useState<FactList>(createFactList());
  const [getWorkloadFacts] = useGetWorkloadFactsMutation();
  const [postWorkloadFact] = usePostWorkloadFactsMutation();
  const [deleteWorkloadFacts] = useDeleteWorkloadFactsMutation();
  const { showError, showSuccess } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  // Fetch initial fact list
  useEffect(() => {
    if (cluster) {
      getWorkloadFacts({
        cluster,
        namespace,
        workload,
        kind,
      })
        .unwrap()
        .then(setFactList)
        .catch((error) => {
          console.error(error);
          showError({ summary: 'Error', detail: 'Failed to fetch facts.' });
        });
    }
  }, [cluster, namespace, workload, kind]);

  const handleSubmit = async (newFact: Fact) => {
    try {
      const updatedFactList = {
        ...factList,
        facts: [...factList.facts, newFact],
      };
      setFactList(updatedFactList);

      await postWorkloadFact({
        cluster,
        namespace,
        workload,
        kind,
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
        await postWorkloadFact({
          cluster,
          namespace,
          workload,
          kind,
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
            await deleteWorkloadFacts({
              cluster,
              namespace,
              workload,
              kind,
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
