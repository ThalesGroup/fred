//! Test-only Temporal wire boundary. Records actual SDK StartWorkflowExecution requests.
use axum::{
    Router,
    body::Bytes,
    http::{StatusCode, header},
    response::IntoResponse,
};
use prost::Message;
use std::io::Read;
use std::sync::{
    Arc,
    atomic::{AtomicU16, Ordering},
};
use temporalio_common::protos::temporal::api::workflowservice::v1::{
    StartWorkflowExecutionRequest, StartWorkflowExecutionResponse,
};
use tokio::sync::Mutex;

pub struct Temporal {
    pub url: String,
    pub starts: Arc<Mutex<Vec<StartWorkflowExecutionRequest>>>,
    pub status: Arc<AtomicU16>,
    task: tokio::task::JoinHandle<()>,
}
impl Drop for Temporal {
    fn drop(&mut self) {
        self.task.abort();
    }
}
impl Temporal {
    pub async fn start() -> Self {
        let starts = Arc::new(Mutex::new(Vec::new()));
        let captured = starts.clone();
        let status = Arc::new(AtomicU16::new(0));
        let reply_status = status.clone();
        let app = Router::new().fallback(move |uri: axum::http::Uri, body: Bytes| {
            let captured = captured.clone();
            let reply_status = reply_status.clone();
            async move {
                if uri.path().ends_with("/GetSystemInfo") {
                    return temporalio_client::tonic::Status::unimplemented(
                        "unknown method GetSystemInfo",
                    )
                    .into_http::<axum::body::Body>();
                }
                assert!(uri.path().ends_with("/StartWorkflowExecution"));
                let mut payload = body[5..].to_vec();
                if body[0] == 1 {
                    let mut decoded = Vec::new();
                    flate2::read::GzDecoder::new(payload.as_slice())
                        .read_to_end(&mut decoded)
                        .unwrap();
                    payload = decoded;
                }
                let request = StartWorkflowExecutionRequest::decode(payload.as_slice()).unwrap();
                captured.lock().await.push(request);
                let code = reply_status.load(Ordering::SeqCst);
                if code != 0 {
                    return temporalio_client::tonic::Status::new(
                        temporalio_client::tonic::Code::from_i32(code.into()),
                        "fixture refusal",
                    )
                    .into_http::<axum::body::Body>();
                }
                let data = StartWorkflowExecutionResponse {
                    run_id: "fixture-run".into(),
                    ..Default::default()
                }
                .encode_to_vec();
                let mut frame = vec![0];
                frame.extend_from_slice(&(data.len() as u32).to_be_bytes());
                frame.extend(data);
                (
                    StatusCode::OK,
                    [
                        (header::CONTENT_TYPE, "application/grpc"),
                        (axum::http::HeaderName::from_static("grpc-status"), "0"),
                    ],
                    frame,
                )
                    .into_response()
            }
        });
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        Self {
            url,
            starts,
            status,
            task,
        }
    }
}
