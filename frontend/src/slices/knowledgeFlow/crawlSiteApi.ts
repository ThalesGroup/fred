import { knowledgeFlowApi } from "./knowledgeFlowOpenApi";

export type CrawlSiteRequest = {
  site_url: string;
  directory_name: string;
  processing_profile: "fast" | "medium" | "rich";
  max_depth: number;
  max_pages: number;
  restrict_to_domain: boolean;
  respect_robots_txt: boolean;
};

export type CrawlRun = {
  id: string;
  source_id: string;
  status: "pending" | "running" | "completed" | "failed";
  started_at?: string | null;
  finished_at?: string | null;
  discovered_count: number;
  fetched_count: number;
  extracted_count: number;
  failed_count: number;
  document_uids: string[];
  error?: string | null;
};

export type CrawlSiteResponse = {
  resource: {
    id: string;
    name: string;
    type: string;
    status: string;
  };
  run: CrawlRun;
};

export type CrawlRunStatusResponse = {
  run: CrawlRun;
  ui_status: "Crawling in progress" | "Ready" | "Failed";
};

export const crawlSiteApi = knowledgeFlowApi.injectEndpoints({
  endpoints: (build) => ({
    crawlSite: build.mutation<CrawlSiteResponse, CrawlSiteRequest>({
      query: (body) => ({
        url: "/knowledge-flow/v1/resources/crawl-site",
        method: "POST",
        body,
      }),
    }),
    getCrawlSiteRun: build.query<CrawlRunStatusResponse, string>({
      query: (runId) => ({ url: `/knowledge-flow/v1/resources/crawl-site/${runId}` }),
    }),
  }),
});

export const { useCrawlSiteMutation, useGetCrawlSiteRunQuery } = crawlSiteApi;
