import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { PageBodyWrapper } from '../common/PageBodyWrapper.tsx';
import { useNamespaceFactHandlers } from '../hooks/useNamespaceFactHandlers.tsx';
import { FactsPageLayout } from '../components/FactsPageLayout.tsx';

export const FactsNamespace: React.FC = () => {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const clusterFullName = searchParams.get("cluster");
  const namespace = searchParams.get("namespace");

  const { factList, handleSubmit, handleEdit, handleDelete } = useNamespaceFactHandlers({
    cluster: clusterFullName!,
    namespace: namespace!,
  });

  const [showForm, setShowForm] = useState(false);
  const handleToggleForm = () => setShowForm((prev) => !prev);
  return (
    <PageBodyWrapper>
      <FactsPageLayout
        title="Namespace Facts"
        factList={factList}
        onSubmit={handleSubmit}
        onEdit={handleEdit}
        onDelete={handleDelete}
        showForm={showForm}
        toggleForm={handleToggleForm}
      />
    </PageBodyWrapper>
  );
};

