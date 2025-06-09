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

import { PageBodyWrapper } from "../common/PageBodyWrapper"
import { TopBar } from "../common/TopBar"
import MetricsDashboard from "../components/monitoring/MetricDashboard"

export const Monitoring = () => {
     return (
        <PageBodyWrapper>
            <TopBar
                    title="Monitoring Overview"
                    description="Monitor and analyze your clusters' cost, carbon, and energy metrics"
                    backgroundUrl=""
                  ></TopBar>
                  <MetricsDashboard />
        </PageBodyWrapper>
     )
}