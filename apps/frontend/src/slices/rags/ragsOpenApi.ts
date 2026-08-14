import { ragsApi as api } from "./ragsApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    health: build.query<HealthApiResponse, HealthApiArg>({
      query: () => ({ url: `/rags-services/v1/health` }),
    }),
    informationSystemListUpdates: build.query<
      InformationSystemListUpdatesApiResponse,
      InformationSystemListUpdatesApiArg
    >({
      query: () => ({ url: `/rags-services/v1/information-system/updates` }),
    }),
    getInformationSystemsSummary: build.query<
      GetInformationSystemsSummaryApiResponse,
      GetInformationSystemsSummaryApiArg
    >({
      query: () => ({ url: `/rags-services/v1/information-system/summary` }),
    }),
    getInformationSystemsDetails: build.query<
      GetInformationSystemsDetailsApiResponse,
      GetInformationSystemsDetailsApiArg
    >({
      query: (queryArg) => ({ url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}` }),
    }),
    updateInformationSystem: build.mutation<UpdateInformationSystemApiResponse, UpdateInformationSystemApiArg>({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}`,
        method: "PUT",
        body: queryArg.informationSystem,
      }),
    }),
    deleteInformationSystem: build.mutation<DeleteInformationSystemApiResponse, DeleteInformationSystemApiArg>({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}`,
        method: "DELETE",
      }),
    }),
    patchInformationSystem: build.mutation<PatchInformationSystemApiResponse, PatchInformationSystemApiArg>({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}`,
        method: "PATCH",
        body: queryArg.informationSystemPatchRequest,
        params: {
          agent_name: queryArg.agentName,
        },
      }),
    }),
    createInformationSystemRagsServicesV1InformationSystemPost: build.mutation<
      CreateInformationSystemRagsServicesV1InformationSystemPostApiResponse,
      CreateInformationSystemRagsServicesV1InformationSystemPostApiArg
    >({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system`,
        method: "POST",
        body: queryArg.informationSystemWithoutUid,
      }),
    }),
    getInformationSystemAssessmentSynthesis: build.query<
      GetInformationSystemAssessmentSynthesisApiResponse,
      GetInformationSystemAssessmentSynthesisApiArg
    >({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}/assessment/synthesis`,
      }),
    }),
    getInformationSystemField: build.query<GetInformationSystemFieldApiResponse, GetInformationSystemFieldApiArg>({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}/field`,
        params: {
          path: queryArg.path,
        },
      }),
    }),
    addInformationSystemDocuments: build.mutation<
      AddInformationSystemDocumentsApiResponse,
      AddInformationSystemDocumentsApiArg
    >({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}/documents`,
        method: "POST",
        body: queryArg.informationSystemDocumentsAdd,
      }),
    }),
    removeInformationSystemDocuments: build.mutation<
      RemoveInformationSystemDocumentsApiResponse,
      RemoveInformationSystemDocumentsApiArg
    >({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/${queryArg.informationSystemUid}/documents`,
        method: "DELETE",
        body: queryArg.informationSystemDocumentsRemove,
      }),
    }),
    removeDocumentFromAllInformationSystems: build.mutation<
      RemoveDocumentFromAllInformationSystemsApiResponse,
      RemoveDocumentFromAllInformationSystemsApiArg
    >({
      query: (queryArg) => ({
        url: `/rags-services/v1/information-system/documents/${queryArg.documentUid}`,
        method: "DELETE",
      }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as ragsApi };
export type HealthApiResponse = /** status 200 Successful Response */ {
  [key: string]: string;
};
export type HealthApiArg = void;
export type InformationSystemListUpdatesApiResponse = /** status 200 Successful Response */ InformationSystemUpdate[];
export type InformationSystemListUpdatesApiArg = void;
export type GetInformationSystemsSummaryApiResponse = /** status 200 Successful Response */ InformationSystemSummary[];
export type GetInformationSystemsSummaryApiArg = void;
export type GetInformationSystemsDetailsApiResponse = /** status 200 Successful Response */ InformationSystem;
export type GetInformationSystemsDetailsApiArg = {
  informationSystemUid: string;
};
export type UpdateInformationSystemApiResponse = /** status 200 Successful Response */ any;
export type UpdateInformationSystemApiArg = {
  informationSystemUid: string;
  informationSystem: InformationSystem;
};
export type DeleteInformationSystemApiResponse = unknown;
export type DeleteInformationSystemApiArg = {
  informationSystemUid: string;
};
export type PatchInformationSystemApiResponse = /** status 200 Successful Response */ InformationSystemUpdate;
export type PatchInformationSystemApiArg = {
  informationSystemUid: string;
  agentName: string;
  informationSystemPatchRequest: InformationSystemPatchRequest;
};
export type CreateInformationSystemRagsServicesV1InformationSystemPostApiResponse =
  /** status 201 Successful Response */ any;
export type CreateInformationSystemRagsServicesV1InformationSystemPostApiArg = {
  informationSystemWithoutUid: InformationSystemWithoutUid;
};
export type GetInformationSystemAssessmentSynthesisApiResponse =
  /** status 200 Successful Response */ MarkdownContentResponse;
export type GetInformationSystemAssessmentSynthesisApiArg = {
  informationSystemUid: string;
};
export type GetInformationSystemFieldApiResponse = /** status 200 Successful Response */ any;
export type GetInformationSystemFieldApiArg = {
  informationSystemUid: string;
  /** Chemin du champ en notation pointée. Exemples : `assessment.technical_details.performance.scalability`, `gap.cloud_public`, `recommandations.general` */
  path: string;
};
export type AddInformationSystemDocumentsApiResponse = /** status 200 Successful Response */ any;
export type AddInformationSystemDocumentsApiArg = {
  informationSystemUid: string;
  informationSystemDocumentsAdd: InformationSystemDocumentsAdd;
};
export type RemoveInformationSystemDocumentsApiResponse = /** status 200 Successful Response */ any;
export type RemoveInformationSystemDocumentsApiArg = {
  informationSystemUid: string;
  informationSystemDocumentsRemove: InformationSystemDocumentsRemove;
};
export type RemoveDocumentFromAllInformationSystemsApiResponse = /** status 200 Successful Response */ any;
export type RemoveDocumentFromAllInformationSystemsApiArg = {
  documentUid: string;
};
export type InformationSystemUpdate = {
  /** Indique si la mise à jour a été réalisée avec succès */
  success?: boolean;
  /** Message décrivant la mise à jour effectuée */
  message: string;
  /** Liste des champs modifiés lors de cette mise à jour */
  updated_fields?: string[];
  /** UID du système d'information concerné par la mise à jour */
  information_system_uid: string;
  /** Horodatage de la mise à jour */
  timestamp?: string;
  /** Utilisateur ayant déclenché la mise à jour */
  user: string;
  /** Nom de l'agent (humain ou technique) ayant effectué la mise à jour */
  agent_name: string;
  /** Nom de l'API ou du service à l'origine de la mise à jour */
  api_name: string;
  /** Nom de l'action réalisée */
  action_type: string;
  /** Liste des modifications lors de cette mise à jour */
  updated_value?: string[];
  /** Nom du système d'information concerné par la mise à jour */
  information_system_name: string;
  /** Valeur précédente, avant changement */
  previous_value: string[];
  /** Valeur complète du champ, après changement */
  full_updated_value: string[];
};
export type AssessmentSummary = {
  /** URL de la synthèse d'évaluation du système d'information */
  assessment_synthesis_url?: string | null;
  /** URL de la synthèse des similarités du système d'information */
  assessment_similarities_url?: string | null;
  /** URL de la synthèse des contradictions du système d'information */
  assessment_contradictions_url?: string | null;
  /** Nombre de similarités */
  similarities?: number;
  /** Nombre de contradictions */
  contradictions?: number;
};
export type GapSummary = {
  /** Nombre de composants analysés dans les politiques techniques */
  technical_policies?: number;
  /** Nombre de prérequis analysés par rapport à un cloud privé */
  private_cloud_requirements?: number;
  /** Nombre de services analysés par rapport à un cloud public */
  public_cloud_recommendations?: number;
};
export type RecommendationsSummary = {
  /** Nombre de recommandations pour la migration vers un cloud privé */
  private_cloud_migration_recommandation?: number;
  /** Nombre de recommandations pour la migration vers un cloud public */
  public_cloud_migration_recommandation?: number;
  /** Nombre de recommandations pour la conformité avec une politique technique */
  technical_policy_recommandation?: number;
  /** Nombre de recommandations pour les écarts entre les documents et la CMDB */
  contradiction_recommandation?: number;
};
export type PlanStatus = "solved" | "degraded";
export type PlanificationSummary = {
  has_plan?: boolean;
  status?: PlanStatus | null;
  nombre_etapes?: number | null;
};
export type InformationSystemDocument = {
  /** UID du document dans Knowledge Flow */
  document_uid: string;
  /** Nom du document (copie pour affichage rapide) */
  document_name?: string | null;
};
export type ConfidenceLevel = "CRITICAL" | "LOW" | "MEDIUM" | "HIGH";
export type InformationSystemSummary = {
  /** UID du système d'information */
  information_system_uid: string;
  /** Nom du système d'information */
  information_system: string;
  /** Nom de la librairie liée au système d'information */
  library_tag_id: string;
  /** Résumé de l'évaluation du système d'information */
  assessment?: AssessmentSummary;
  /** Résumé des écarts */
  gap?: GapSummary;
  /** Résumé des recommandations */
  recommendations?: RecommendationsSummary;
  /** Résumé du plan de migration Chronos */
  planification?: PlanificationSummary;
  /** Documents associés au SI (DAT, MEX, CMDB ...) */
  documents?: {
    [key: string]: InformationSystemDocument[];
  };
  /** Score global de confiance */
  overall_score?: number;
  /** Niveau de confiance global */
  confidence_level?: ConfidenceLevel;
};
export type SystemDetails = {
  /** Systèmes d'exploitation avec versions */
  os?: string[];
  /** Langages de programmation avec versions */
  languages?: string[];
  /** Frameworks avec versions */
  frameworks?: string[];
  /** Bibliothèques/dépendances avec versions */
  libraries?: string[];
  /** Serveurs applicatifs/web avec versions */
  servers?: string[];
  /** Technologies de conteneurisation */
  containers?: string[];
  /** Modules/composants logiciels */
  modules?: string[];
};
export type DataDetails = {
  /** SGBD avec versions */
  databases?: string[];
  /** Noms de tables/collections/schémas */
  schemas?: string[];
  /** Solutions de stockage */
  storage?: string[];
  /** Mécanismes de sauvegarde */
  backup?: string[];
  /** Configurations de réplication */
  replication?: string[];
};
export type IntegrationDetails = {
  /** Types d'API et standards */
  apis?: string[];
  /** Protocoles réseau avec versions */
  protocols?: string[];
  /** Ports TCP/UDP avec services */
  ports?: string[];
  /** Systèmes de messaging */
  messaging?: string[];
  /** Formats d'échange de données */
  formats?: string[];
  /** URLs et endpoints */
  endpoints?: string[];
};
export type SecurityDetails = {
  /** Méthodes d'authentification */
  authentication?: string[];
  /** Mécanismes d'autorisation */
  authorization?: string[];
  /** Protocoles et algorithmes de chiffrement */
  encryption?: string[];
  /** Outils de gestion des secrets */
  secrets?: string[];
  /** Sécurité réseau (firewall, WAF) */
  network_security?: string[];
};
export type OperationsDetails = {
  /** Outils de monitoring et métriques */
  monitoring?: string[];
  /** Systèmes de gestion des logs */
  logging?: string[];
  /** Méthodes et outils de déploiement */
  deployment?: string[];
  /** Procédures opérationnelles */
  procedures?: string[];
  /** Jobs batch et schedulés */
  batch_jobs?: string[];
  /** Liste des contacts opérationnels */
  contacts?: string[];
};
export type PerformanceDetails = {
  /** Stratégies de scalabilité */
  scalability?: string[];
  /** Solutions de cache */
  cache?: string[];
  /** SLA et SLO */
  sla?: string[];
  /** Load balancing */
  load_balancing?: string[];
  /** Optimisations diverses */
  optimizations?: string[];
};
export type ConfigurationDetails = {
  /** Fichiers de configuration */
  files?: string[];
  /** Variables d'environnement */
  env_vars?: string[];
  /** Profils/environnements */
  profiles?: string[];
  /** Paramètres de tuning */
  tuning_params?: string[];
  /** Seuils et limites */
  thresholds?: string[];
};
export type TechnicalDetails = {
  /** Date d'extraction */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  system?: SystemDetails;
  data?: DataDetails;
  integration?: IntegrationDetails;
  security?: SecurityDetails;
  operations?: OperationsDetails;
  performance?: PerformanceDetails;
  configuration?: ConfigurationDetails;
};
export type TechnicalTheme =
  | "Syst\u00E8me"
  | "Donn\u00E9es"
  | "Int\u00E9gration"
  | "S\u00E9curit\u00E9"
  | "Exploitation"
  | "Performance"
  | "Configuration"
  | "CMDB";
export type Similarity = {
  /** Catégorie technique de la similarité */
  theme: TechnicalTheme;
  /** Description de la similarité */
  description: string;
};
export type Similarities = {
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** Liste des similarités entre les documents analysés */
  similarities?: Similarity[];
};
export type Contradiction = {
  /** Conflit technique précis */
  issue: string;
  /** Spécification technique dans A */
  doc_a_spec: string;
  /** Spécification technique dans B */
  doc_b_spec: string;
  /** Catégorie technique de la contradiction */
  theme: TechnicalTheme;
};
export type Contradictions = {
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** Liste des contradictions entre les documents analysés */
  contradictions?: Contradiction[];
};
export type Assessment = {
  /** URL de la synthèse d'évaluation du système d'information */
  assessment_synthesis_url?: string | null;
  /** URL de la synthèse des similarités du système d'information */
  assessment_similarities_url?: string | null;
  /** URL de la synthèse des contradictions du système d'information */
  assessment_contradictions_url?: string | null;
  /** Détails techniques du système d'information */
  technical_details?: TechnicalDetails;
  /** Similarités entre les documents analysés */
  similarities?: Similarities;
  /** Contradictions entre les documents analysés */
  contradictions?: Contradictions;
};
export type TechnicalPolicy = {
  /** Le nom du middleware et sa version */
  component: string;
  /** Le statut du composant (format : en toutes lettres avec les abréviations entre parenthèse). Non mentionné s'il n'y en pas */
  status?: string;
  /** La version recommandée du composant si mentionnée. Mettre à None si non mentionnée. */
  recommanded_version?: string | null;
  /** Analyse */
  analysis: string;
};
export type TechnicalPolicies = {
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** Nom de la politique technique */
  technical_policy_name?: string | null;
  /** UID de la politique technique */
  technical_policy_uid?: string | null;
  /** Liste de composants analysés dans la politique technique */
  components?: TechnicalPolicy[];
};
export type ComplianceStatus = "Respect\u00E9" | "Non-respect\u00E9";
export type CloudRequirement = {
  /** Titre du prérequis */
  title: string;
  /** Description du prérequis */
  description: string;
  /** Statut du prérequis : Respecté ou Non respecté */
  status?: ComplianceStatus | null;
  /** Commentaire sur le prérequis */
  comment?: string | null;
};
export type PrivateCloudRequirements = {
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** UID du cloud cible */
  target_cloud_uid?: string | null;
  /** Nom du cloud cible */
  target_cloud_name?: string | null;
  /** Liste des prérequis */
  requirements?: CloudRequirement[];
};
export type PublicCloudRequirement = {
  /** Nom du prérequis */
  title: string;
  /** Description du prérequis */
  description: string;
  /** Commentaire sur le prérequis */
  comment: string;
};
export type PublicCloudServiceRecommendation = {
  /** Nom de la catégorie */
  cloud_category: string;
  /** Nom du service cloud */
  cloud_service: string;
  /** Nom du service équivalent dans le SI */
  equivalent_si_service: string;
  /** Source de l'information */
  source: string;
  /** Justification du choix du service cloud */
  justification: string;
  /** Remarque sur le service cloud */
  remark: string;
  /** Liste des prérequis */
  requirements: PublicCloudRequirement[];
};
export type PublicCloudRecommendations = {
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** UID du cloud public cible */
  target_cloud_uid?: string | null;
  /** Nom du cloud public cible */
  target_cloud_name?: string | null;
  /** Liste des recommendations de services cloud public */
  recommendations?: PublicCloudServiceRecommendation[];
};
export type Gap = {
  /** Analyse de la conformité par rapport aux politiques techniques */
  technical_policies?: TechnicalPolicies;
  /** Analyse des prérequis d'un cloud cible privé */
  private_cloud_requirements?: PrivateCloudRequirements;
  /** Analyse de compatibilité avec les services d'un cloud public */
  public_cloud_recommendations?: PublicCloudRecommendations;
};
export type RequirementStatus = "respect\u00E9" | "non_respect\u00E9";
export type CloudMigrationCriticality = "bloquant" | "majeur" | "mineur";
export type ImpactDimension = "performance" | "security" | "availability" | "cost";
export type CloudMigrationImpact = {
  /** Dimension d'impact analysée */
  dimension: ImpactDimension;
  /** Description concrète de l'impact si le prérequis n'est pas traité */
  description: string;
};
export type MigrationPhase = "pr\u00E9paration" | "mise_en_conformit\u00E9" | "validation";
export type MigrationActionStep = {
  /** Phase de migration concernée */
  phase: MigrationPhase;
  /** Actions techniques concrètes à réaliser */
  actions: string;
  /** Livrables attendus à l'issue de cette phase */
  deliverables: string;
  /** Critères et métriques de validation de succès */
  validation_criteria: string;
};
export type PrivateCloudMigrationRecommendation = {
  /** Titre du prérequis de migration */
  requirement_title: string;
  /** Statut de conformité du prérequis */
  status: RequirementStatus;
  /** Niveau de criticité pour la migration */
  criticality: CloudMigrationCriticality;
  /** Synthèse de la situation et implications pour la migration */
  analysis: string;
  /** Analyse des impacts si non traité (uniquement pour les prérequis non respectés) */
  impacts?: CloudMigrationImpact[] | null;
  /** Actions concrètes et priorisées pour traiter le prérequis */
  recommendation: string;
  /** Plan d'action détaillé en 3 phases (uniquement pour les prérequis non respectés) */
  action_plan?: MigrationActionStep[] | null;
  /** Diagramme Mermaid illustrant le flux de migration (uniquement pour les prérequis non respectés) */
  mermaid_flow?: string | null;
};
export type CloudTransformationTheme =
  | "network_connectivity"
  | "security_iam"
  | "data_storage"
  | "integration_middleware"
  | "observability_operations"
  | "organization_governance";
export type Severity = "faible" | "moyen" | "\u00E9lev\u00E9" | "critique";
export type Priority = "haute" | "moyenne" | "basse";
export type CloudMigrationActionStep = {
  /** Numéro de l'étape dans le plan d'action */
  step: number;
  /** Description concrète et vérifiable de l'action à entreprendre */
  action: string;
  /** Niveau de priorité de cette action */
  priority: Priority;
};
export type RiskLevel = "faible" | "moyen" | "\u00E9lev\u00E9";
export type CloudMigrationRiskScenario = {
  /** Nom du scénario évalué */
  scenario: string;
  /** Liste des avantages techniques et opérationnels de ce scénario */
  advantages: string[];
  /** Liste des risques identifiés pour ce scénario */
  risks: string[];
  /** Niveau de risque global du scénario */
  risk_level: RiskLevel;
};
export type ServiceLink = {
  /** Catégorie du service cloud concerné (ex: base_de_données_managée, stockage_objet…) */
  cloud_category?: string | null;
  /** Nom ou type du service cloud concerné, si disponible dans le JSON d'entrée */
  cloud_service?: string | null;
  /** Nom de l'équivalent dans le SI, si présent dans le JSON d'entrée */
  equivalent_si_service?: string | null;
};
export type PublicCloudMigrationRecommendation = {
  /** Thème de la mesure de transformation (network_connectivity, security_iam, etc.) */
  theme: CloudTransformationTheme;
  /** Description synthétique de la mesure de transformation ou du problème à adresser */
  issue: string;
  /** Niveau de gravité/importance de cette mesure de transformation */
  severity: Severity;
  /** Analyse du contexte et des impacts si la mesure n'est pas mise en œuvre (technique, sécurité, exploitation, organisationnel) */
  context_analysis: string;
  /** Solution de transformation recommandée avec justification */
  recommendation: string;
  /** Liste des étapes concrètes pour mettre en œuvre la mesure de transformation */
  action_plan?: CloudMigrationActionStep[];
  /** Diagramme Mermaid montrant la logique de mise en œuvre de la mesure et ses dépendances (syntaxe complète du diagramme) */
  mermaid_flow: string;
  /** Évaluation des risques pour les scénarios possibles */
  risks_considerations?: CloudMigrationRiskScenario[];
  /** Services cloud principalement concernés par cette mesure de transformation */
  related_services?: ServiceLink[];
};
export type ConformityStatus = "conforme" | "non-conforme" | "non-applicable";
export type ImpactCategory = "security" | "support" | "compatibility" | "technical" | "operational";
export type Impact = {
  /** Catégorie de l'impact */
  category: ImpactCategory;
  /** Description détaillée de l'impact */
  description: string;
};
export type ActionStepTechnicalPolicy = {
  /** Numéro de l'étape dans le plan d'action */
  step: number;
  /** Description concrète et vérifiable de l'action à entreprendre */
  action: string;
  /** Niveau de priorité de cette action */
  priority: Priority;
  /** Prérequis ou dépendances nécessaires avant cette étape */
  prerequisites: string;
  /** Liste des composants impactés par cette action */
  affected_components: string[];
};
export type RiskScenario = {
  /** Nom du scénario évalué */
  scenario: string;
  /** Liste des avantages techniques et opérationnels de ce scénario */
  advantages: string[];
  /** Liste des risques identifiés pour ce scénario */
  risks: string[];
  /** Niveau de risque global du scénario */
  risk_level: RiskLevel;
};
export type TechnicalPolicyRecommendation = {
  /** Nom du middleware ou composant technique */
  component_name: string;
  /** Version actuellement utilisée */
  current_version?: string | null;
  /** Version recommandée par la politique technique */
  recommended_version?: string | null;
  /** Statut dans la politique (Standard, Obsolète, Déprécié, En évaluation, etc.) */
  policy_status?: string | null;
  /** Statut de conformité */
  conformity: ConformityStatus;
  /** Niveau de priorité de la mise en conformité */
  priority: Severity;
  /** Synthèse de la situation : nature de l'écart, implications du non-alignement */
  evaluation: string;
  /** Analyse des impacts (uniquement pour les cas non-conformes) */
  impacts?: Impact | null;
  /** Action claire et justifiée basée sur l'analyse des risques et la politique */
  recommendation: string;
  /** Plan d'action détaillé (uniquement pour les cas non-conformes) */
  action_plan?: ActionStepTechnicalPolicy[] | null;
  /** Diagramme Mermaid du flux de migration avec phases et validations (uniquement pour les cas non-conformes) */
  mermaid_flow?: string | null;
  /** Évaluation des risques : exactement 3 scénarios (maintenir version actuelle, migrer vers recommandée, solution alternative) - uniquement pour les cas non-conformes */
  risks_considerations?: RiskScenario[] | null;
};
export type ActionStepContradiction = {
  /** Numéro de l'étape dans le plan d'action */
  step: number;
  /** Description concrète et vérifiable de l'action à entreprendre */
  action: string;
  /** Niveau de priorité de cette action */
  priority: Priority;
};
export type ContradictionRecommendation = {
  /** Thème de la contradiction (système, données, intégration, cmdb) */
  theme: string;
  /** Description de la contradiction identifiée */
  issue: string;
  /** Niveau de gravité de la contradiction */
  severity: Severity;
  /** Analyse détaillée de la divergence, son impact et les composants affectés */
  conflict_analysis: string;
  /** Solution technique recommandée avec justification */
  recommendation: string;
  /** Liste des étapes concrètes pour résoudre la contradiction */
  action_plan: ActionStepContradiction[];
  /** Diagramme Mermaid montrant la logique de résolution (syntaxe complète du diagramme) */
  mermaid_flow: string;
  /** Évaluation des risques pour les différents scénarios possibles */
  risks_considerations: RiskScenario[];
};
export type Recommendations = {
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** Liste des recommandations pour la migration vers un cloud privé */
  private_cloud_migration_recommandation?: PrivateCloudMigrationRecommendation[];
  /** Liste des recommandations pour la transformation du SI en vue d'une migration vers un cloud public */
  public_cloud_migration_recommandation?: PublicCloudMigrationRecommendation[];
  /** Liste des recommandations pour la conformité avec une politique technique */
  technical_policy_recommandation?: TechnicalPolicyRecommendation[];
  /** Liste des recommandations pour les écarts entre les documents et la CMDB */
  contradiction_recommandation?: ContradictionRecommendation[];
};
export type PlanPhase = "preparation" | "mise_en_conformite" | "migration" | "validation" | "production";
export type MigrationStepDetail = {
  /** Ordre d'exécution issu du solveur PDDL */
  order: number;
  /** Identifiant de l'action PDDL brute */
  pddl_action: string;
  /** Libellé lisible de l'action */
  label: string;
  /** Ce que fait concrètement cette étape */
  description: string;
  /** Phase de migration */
  phase: PlanPhase;
  composants_impactes?: string[];
  /** Actions PDDL dont cette étape dépend */
  prerequis?: string[];
  livrables?: string[];
};
export type RetexLesson = {
  /** Aspect technique principal concerné (ex: réseau, sécurité, données) */
  theme: string;
  /** Ce qui a été appris dans les migrations terrain */
  enseignement: string;
  /** Action concrète à appliquer dans ce plan */
  recommandation: string;
};
export type MigrationPlanPresentation = {
  /** Synthèse exécutive du plan */
  synthese_executive: string;
  /** Points de vigilance majeurs */
  points_critiques: string[];
  /** Étapes ordonnées du plan */
  etapes: MigrationStepDetail[];
  /** Leçons tirées du RETEX terrain */
  enseignements_retex: RetexLesson[];
};
export type PddlFiles = {
  /** Contenu domain.pddl */
  domain: string;
  /** Contenu problem.pddl */
  problem: string;
};
export type MigrationPlan = {
  created?: string;
  updated?: string;
  status: PlanStatus;
  fd_solved: boolean;
  nombre_etapes?: number | null;
  presentation: MigrationPlanPresentation;
  pddl_files: PddlFiles;
};
export type Planification = {
  created?: string;
  updated?: string;
  migration_plan?: MigrationPlan | null;
};
export type CmdbPenalty = {
  has_cmdb?: boolean;
  penalty_applied?: number;
  reason?: string;
};
export type MexPenalty = {
  has_mex?: boolean;
  penalty_applied?: number;
  reason?: string;
};
export type SiIdentity = {
  score?: number;
  has_name?: boolean;
  has_owner?: boolean;
  has_responsible_team?: boolean;
  has_functional_scope?: boolean;
  comment?: string;
};
export type InterSiDependencies = {
  score?: number;
  comment?: string;
};
export type EnvironmentsCoverage = {
  score?: number;
  environments_found?: string[];
  comment?: string;
};
export type DocumentFreshness = {
  score?: number;
  oldest_document_date?: string | null;
  comment?: string;
};
export type DatDetails = {
  si_identity?: SiIdentity;
  inter_si_dependencies?: InterSiDependencies;
  environments_coverage?: EnvironmentsCoverage;
  freshness?: DocumentFreshness;
};
export type DatScore = {
  score?: number;
  weight?: number;
  details?: DatDetails;
};
export type ProcedureCoverage = {
  score?: number;
  has_start_stop?: boolean;
  has_backup_restore?: boolean;
  has_supervision?: boolean;
  has_incident_handling?: boolean;
  has_upgrade?: boolean;
  comment?: string;
};
export type Responsibilities = {
  score?: number;
  comment?: string;
};
export type SlaAndAlerts = {
  score?: number;
  comment?: string;
};
export type MexDetails = {
  procedure_coverage?: ProcedureCoverage;
  responsibilities?: Responsibilities;
  sla_and_alerts?: SlaAndAlerts;
  freshness?: DocumentFreshness;
};
export type MexScore = {
  score?: number;
  weight?: number;
  details?: MexDetails;
};
export type CiRelationships = {
  score?: number;
  has_relationships?: boolean;
  comment?: string;
};
export type CiCoverage = {
  score?: number;
  ci_types_found?: string[];
  coverage_percent?: number;
  comment?: string;
};
export type CmdbFreshness = {
  score?: number;
  age_days?: number | null;
  reference_date_found?: string | null;
  comment?: string;
};
export type CmdbDetails = {
  ci_relationships?: CiRelationships;
  ci_coverage?: CiCoverage;
  freshness?: CmdbFreshness;
};
export type CmdbScore = {
  score?: number;
  weight?: number;
  details?: CmdbDetails;
};
export type ConfidenceScoreAxes = {
  dat?: DatScore;
  mex?: MexScore;
  cmdb?: CmdbScore;
};
export type ContradictionPenalty = {
  penalty_applied?: number;
  contradiction_count?: number;
  comment?: string;
};
export type EvaEnrichment = {
  applied?: boolean;
  contradiction_penalty?: ContradictionPenalty;
  score_after_eva?: number;
};
export type ConfidenceScore = {
  created?: string;
  updated?: string;
  overall_score?: number;
  confidence_level?: ConfidenceLevel;
  is_reliable_for_migration?: boolean;
  cmdb_penalty?: CmdbPenalty;
  mex_penalty?: MexPenalty;
  axes?: ConfidenceScoreAxes;
  eva_enrichment?: EvaEnrichment;
};
export type InformationSystem = {
  /** Nom du système d'information */
  information_system: string;
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** Représentation métier de l'évaluation du système d'information */
  assessment?: Assessment;
  /** Représentation métier des écarts avec des politiques techniques, un cloud privé et un cloud public */
  gap?: Gap;
  /** Recommandations */
  recommandations?: Recommendations;
  /** Plan de migration cloud */
  planification?: Planification;
  /** Score de confiance du SI calculé par EVA */
  confidence_score?: ConfidenceScore;
  /** Historique des mises à jour du système d'information */
  updates_history?: InformationSystemUpdate[];
  /** Liste des documents associés au système d'information (DAT, MEX, CMDB, etc.) */
  documents?: {
    [key: string]: InformationSystemDocument[];
  };
  /** UID du tag (librairie) utilisée par le SI */
  library_tag_id: string;
  /** UID du système d'information */
  information_system_uid: string;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: any;
  ctx?: object;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type PatchOperation = {
  op: "add" | "replace" | "remove";
  path: string;
  value?: any[] | null;
};
export type InformationSystemPatchRequest = {
  operations: PatchOperation[];
};
export type InformationSystemWithoutUid = {
  /** Nom du système d'information */
  information_system: string;
  /** Date de création */
  created?: string;
  /** Date de mise à jour */
  updated?: string;
  /** Représentation métier de l'évaluation du système d'information */
  assessment?: Assessment;
  /** Représentation métier des écarts avec des politiques techniques, un cloud privé et un cloud public */
  gap?: Gap;
  /** Recommandations */
  recommandations?: Recommendations;
  /** Plan de migration cloud */
  planification?: Planification;
  /** Score de confiance du SI calculé par EVA */
  confidence_score?: ConfidenceScore;
  /** Historique des mises à jour du système d'information */
  updates_history?: InformationSystemUpdate[];
  /** Liste des documents associés au système d'information (DAT, MEX, CMDB, etc.) */
  documents?: {
    [key: string]: InformationSystemDocument[];
  };
  /** UID du tag (librairie) utilisée par le SI */
  library_tag_id: string;
};
export type MarkdownContentResponse = {
  content: string;
};
export type InformationSystemDocumentsAdd = {
  /** Documents à ajouter, organisés par rôle */
  documents?: {
    [key: string]: InformationSystemDocument[];
  };
};
export type InformationSystemDocumentsRemove = {
  /** UID des documents à supprimer, organisés par rôle */
  documents?: {
    [key: string]: string[];
  };
};
export const {
  useHealthQuery,
  useLazyHealthQuery,
  useInformationSystemListUpdatesQuery,
  useLazyInformationSystemListUpdatesQuery,
  useGetInformationSystemsSummaryQuery,
  useLazyGetInformationSystemsSummaryQuery,
  useGetInformationSystemsDetailsQuery,
  useLazyGetInformationSystemsDetailsQuery,
  useUpdateInformationSystemMutation,
  useDeleteInformationSystemMutation,
  usePatchInformationSystemMutation,
  useCreateInformationSystemRagsServicesV1InformationSystemPostMutation,
  useGetInformationSystemAssessmentSynthesisQuery,
  useLazyGetInformationSystemAssessmentSynthesisQuery,
  useGetInformationSystemFieldQuery,
  useLazyGetInformationSystemFieldQuery,
  useAddInformationSystemDocumentsMutation,
  useRemoveInformationSystemDocumentsMutation,
  useRemoveDocumentFromAllInformationSystemsMutation,
} = injectedRtkApi;
