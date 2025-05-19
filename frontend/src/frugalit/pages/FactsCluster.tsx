import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { PageBodyWrapper } from '../../common/PageBodyWrapper.tsx';
import { useClusterFactHandlers } from '../hooks/useClusterFactHandlers.tsx';
import { FactsPageLayout } from '../component/FactsPageLayout.tsx';

export const FactsCluster: React.FC = () => {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const clusterFullName = searchParams.get("cluster");
  const { factList, handleSubmit, handleEdit, handleDelete } = useClusterFactHandlers({
    cluster: clusterFullName!,
  });
  const [showForm, setShowForm] = useState(false);
  const handleToggleForm = () => setShowForm((prev) => !prev);
  return (
    <PageBodyWrapper>
      <FactsPageLayout
        title="Cluster Facts"
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
