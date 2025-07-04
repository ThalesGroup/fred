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
import { useGetWorkloadFactsMutation } from "../slices/api.tsx";
import { useToast } from "../../components/ToastProvider.tsx";
import { useConfirmationDialog } from "../../components/ConfirmationDialogProvider.tsx";
import { useWorkloadFactHandlers } from "../hooks/useWorkloadFactHandlers.tsx";
import { FactsPageLayout } from "../component/FactsPageLayout.tsx";
/*
  This component displays a list of facts for a specific workload.
  It allows the user to add, edit, and delete facts at workload level.
*/
export const FactsWorkload: React.FC = () => {
  const location = useLocation();
  const searchParams = new URLSearchParams(location.search);
  const clusterFullName = searchParams.get("cluster");
  const namespace = searchParams.get("namespace");
  const workload = searchParams.get("workload");
  const kind = searchParams.get("kind");

  const { factList, handleSubmit, handleEdit, handleDelete } = useWorkloadFactHandlers({
    cluster: clusterFullName!,
    namespace: namespace!,
    workload: workload!,
    kind: kind!,
  });

  const [] = useGetWorkloadFactsMutation();
  const [showForm, setShowForm] = useState(false);
  useToast();
  const handleToggleForm = () => setShowForm((prev) => !prev);
  useConfirmationDialog();
  return (
    <FactsPageLayout
      title="Workload Facts"
      factList={factList}
      onSubmit={handleSubmit}
      onEdit={handleEdit}
      onDelete={handleDelete}
      showForm={showForm}
      toggleForm={handleToggleForm}
    />
  );
};
