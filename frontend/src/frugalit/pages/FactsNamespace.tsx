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

import React, { useState } from "react";
import { useLocation } from "react-router-dom";
import { PageBodyWrapper } from "../../common/PageBodyWrapper.tsx";
import { useNamespaceFactHandlers } from "../hooks/useNamespaceFactHandlers.tsx";
import { FactsPageLayout } from "../component/FactsPageLayout.tsx";

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
