//! HTTP server, routing and static file delivery for the v3 dashboard.

use std::fs;
use std::io::Write;
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::thread;
use std::time::Duration;

use crate::http::{Request, Response, read_request};
use crate::json;
use crate::runs::{self, find_run, url_segment};

pub const SERVICE_VERSION: &str = env!("CARGO_PKG_VERSION");

#[derive(Clone, Debug)]
pub struct WebConfig {
    pub bind: String,
    pub data_dir: PathBuf,
    pub plots_dir: PathBuf,
    pub web_dir: PathBuf,
    pub token: Option<String>,
}

impl Default for WebConfig {
    fn default() -> Self {
        Self {
            bind: "127.0.0.1:8080".to_string(),
            data_dir: PathBuf::from("data/v3"),
            plots_dir: PathBuf::from("data/plots"),
            web_dir: PathBuf::from("web/dist"),
            token: None,
        }
    }
}

impl WebConfig {
    pub fn from_env() -> Self {
        let mut config = Self::default();
        if let Ok(value) = std::env::var("AUTOMATA_WEB_BIND") {
            config.bind = value;
        }
        if let Ok(value) = std::env::var("AUTOMATA_DATA_DIR") {
            config.data_dir = PathBuf::from(value);
        }
        if let Ok(value) = std::env::var("AUTOMATA_PLOTS_DIR") {
            config.plots_dir = PathBuf::from(value);
        }
        if let Ok(value) = std::env::var("AUTOMATA_WEB_DIR") {
            config.web_dir = PathBuf::from(value);
        }
        if let Ok(value) = std::env::var("AUTOMATA_WEB_TOKEN")
            && !value.is_empty()
        {
            config.token = Some(value);
        }
        config
    }
}

pub fn serve(config: WebConfig) -> std::io::Result<()> {
    let listener = TcpListener::bind(&config.bind)?;
    eprintln!("automata-web listening on http://{}", config.bind);
    eprintln!("data: {}", config.data_dir.display());
    eprintln!(
        "auth: {}",
        if config.token.is_some() {
            "token required for /api, /files and /plots"
        } else {
            "disabled (bind to localhost or use a reverse proxy)"
        }
    );
    for stream in listener.incoming() {
        match stream {
            Ok(stream) => {
                let config = config.clone();
                thread::spawn(move || handle_connection(stream, &config));
            }
            Err(error) => eprintln!("accept error: {error}"),
        }
    }
    Ok(())
}

pub fn handle_connection(mut stream: TcpStream, config: &WebConfig) {
    let request = match read_request(&mut stream) {
        Ok(request) => request,
        Err(error) => {
            let response = Response::json(
                400,
                format!("{{{}}}", json::field("error", &json::string(&error))),
            );
            let _ = response.write_to(&mut stream);
            return;
        }
    };

    if needs_auth(&request.path) && !authorized(&request, config) {
        let response = Response::json(
            401,
            format!(
                "{{{}}}",
                json::field("error", &json::string("authentication required"))
            ),
        );
        let _ = response.write_to(&mut stream);
        return;
    }

    if request.method == "GET" && request.path == "/api/events" {
        serve_events(&mut stream, config);
        return;
    }

    let response = route(config, &request);
    let _ = response.write_to(&mut stream);
}

pub fn route(config: &WebConfig, request: &Request) -> Response {
    if request.method != "GET" {
        return Response::json(
            405,
            format!(
                "{{{}}}",
                json::field("error", &json::string("only GET is supported"))
            ),
        )
        .with_header("Allow", "GET");
    }

    let path = request.path.as_str();
    if path == "/api/health" {
        return Response::json(
            200,
            format!(
                "{{{},{},{}}}",
                json::field("status", &json::string("ok")),
                json::field("service", &json::string("automata-web")),
                json::field("version", &json::string(SERVICE_VERSION))
            ),
        );
    }
    if path == "/api/runs" {
        return Response::json(200, runs::runs_json(&config.data_dir));
    }
    if let Some(rest) = path.strip_prefix("/api/runs/") {
        return run_route(config, rest);
    }
    if let Some(rest) = path.strip_prefix("/files/runs/") {
        return run_file_route(config, rest);
    }
    if let Some(rest) = path.strip_prefix("/plots/") {
        return plots_route(config, rest);
    }
    static_route(config, path)
}

fn run_route(config: &WebConfig, rest: &str) -> Response {
    let (key, suffix) = match rest.split_once('/') {
        Some((key, suffix)) => (key, Some(suffix)),
        None => (rest, None),
    };
    let key = crate::http::percent_decode(key);
    let Some((directory, summary)) = find_run(&config.data_dir, &key) else {
        return not_found("run not found");
    };
    match suffix {
        None => Response::json(
            200,
            format!(
                "{{{},{}}}",
                json::field("run", &summary.to_json()),
                json::field("manifest", &runs::manifest_json(&directory))
            ),
        ),
        Some("reports") => Response::json(200, runs::reports_json(&directory, &summary)),
        Some(_) => not_found("unknown run resource"),
    }
}

fn run_file_route(config: &WebConfig, rest: &str) -> Response {
    let Some((directory_key, file_name)) = rest.split_once('/') else {
        return not_found("report file not found");
    };
    let directory_key = crate::http::percent_decode(directory_key);
    let file_name = crate::http::percent_decode(file_name);
    if !is_safe_name(&file_name) {
        return not_found("report file not found");
    }
    let Some((directory, _)) = find_run(&config.data_dir, &directory_key) else {
        return not_found("run not found");
    };
    let path = directory.join(&file_name);
    file_response(&path)
}

fn plots_route(config: &WebConfig, rest: &str) -> Response {
    let file_name = crate::http::percent_decode(rest);
    if !is_safe_name(&file_name) {
        return not_found("plot not found");
    }
    file_response(&config.plots_dir.join(file_name))
}

fn static_route(config: &WebConfig, path: &str) -> Response {
    let relative = path.trim_start_matches('/');
    if relative.is_empty() {
        return index_response(config);
    }
    let Some(file) = safe_join(&config.web_dir, relative) else {
        return not_found("not found");
    };
    if file.is_file() {
        return file_response(&file);
    }
    // SPA fallback: unknown extension-less paths return the app shell.
    if Path::new(relative).extension().is_none() {
        return index_response(config);
    }
    not_found("not found")
}

fn index_response(config: &WebConfig) -> Response {
    let index = config.web_dir.join("index.html");
    if index.is_file() {
        return file_response(&index);
    }
    Response::new(
        200,
        "text/html; charset=utf-8",
        include_str!("../assets/dashboard.html"),
    )
}

fn file_response(path: &Path) -> Response {
    match fs::read(path) {
        Ok(bytes) => Response::new(200, content_type(path), bytes),
        Err(_) => not_found("file not found"),
    }
}

fn not_found(message: &str) -> Response {
    Response::json(
        404,
        format!("{{{}}}", json::field("error", &json::string(message))),
    )
}

fn content_type(path: &Path) -> &'static str {
    match path
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| extension.to_ascii_lowercase())
        .as_deref()
    {
        Some("html") | Some("htm") => "text/html; charset=utf-8",
        Some("css") => "text/css; charset=utf-8",
        Some("js") | Some("mjs") => "text/javascript; charset=utf-8",
        Some("json") => "application/json; charset=utf-8",
        Some("md") | Some("txt") => "text/plain; charset=utf-8",
        Some("svg") => "image/svg+xml",
        Some("png") => "image/png",
        Some("jpg") | Some("jpeg") => "image/jpeg",
        Some("webp") => "image/webp",
        Some("ico") => "image/x-icon",
        Some("woff2") => "font/woff2",
        _ => "application/octet-stream",
    }
}

fn safe_join(root: &Path, relative: &str) -> Option<PathBuf> {
    let mut path = root.to_path_buf();
    for part in relative.split('/') {
        if part.is_empty() || part == "." || part == ".." || part.contains('\\') {
            return None;
        }
        path.push(part);
    }
    Some(path)
}

fn is_safe_name(name: &str) -> bool {
    !name.is_empty()
        && name != "."
        && name != ".."
        && !name.contains('/')
        && !name.contains('\\')
        && !name.contains('\0')
}

fn needs_auth(path: &str) -> bool {
    path.starts_with("/api/") || path.starts_with("/files/") || path.starts_with("/plots/")
}

fn authorized(request: &Request, config: &WebConfig) -> bool {
    let Some(expected) = config.token.as_deref() else {
        return true;
    };
    if let Some(value) = request.header("authorization")
        && let Some(token) = value.strip_prefix("Bearer ")
        && constant_time_eq(token.as_bytes(), expected.as_bytes())
    {
        return true;
    }
    if let Some(value) = request.header("x-automata-token")
        && constant_time_eq(value.as_bytes(), expected.as_bytes())
    {
        return true;
    }
    request
        .query_param("token")
        .is_some_and(|token| constant_time_eq(token.as_bytes(), expected.as_bytes()))
}

fn constant_time_eq(left: &[u8], right: &[u8]) -> bool {
    if left.len() != right.len() {
        return false;
    }
    let mut difference = 0_u8;
    for (left, right) in left.iter().zip(right) {
        difference |= left ^ right;
    }
    difference == 0
}

fn serve_events(stream: &mut TcpStream, config: &WebConfig) {
    let _ = stream.set_write_timeout(Some(Duration::from_secs(10)));
    if stream
        .write_all(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream; charset=utf-8\r\nCache-Control: no-cache\r\nConnection: close\r\nX-Accel-Buffering: no\r\n\r\nretry: 3000\n\n",
        )
        .is_err()
    {
        return;
    }
    loop {
        let body = runs::runs_json(&config.data_dir);
        let event = format!("event: runs\ndata: {body}\n\n");
        if stream.write_all(event.as_bytes()).is_err() || stream.flush().is_err() {
            break;
        }
        thread::sleep(Duration::from_secs(2));
    }
}

/// Builds the report URL for tests and documentation examples.
pub fn report_url(run_directory: &str, file_name: &str) -> String {
    format!(
        "/files/runs/{}/{}",
        url_segment(run_directory),
        url_segment(file_name)
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};

    static COUNTER: AtomicU64 = AtomicU64::new(0);

    fn temporary_directory(label: &str) -> PathBuf {
        let unique = COUNTER.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "automata-web-server-{}-{}-{label}-{unique}",
            std::process::id(),
            automata_io::now_unix()
        ));
        fs::create_dir_all(&path).expect("create test directory");
        path
    }

    fn request(method: &str, path: &str) -> Request {
        Request {
            method: method.to_string(),
            path: path.to_string(),
            query: None,
            headers: Vec::new(),
        }
    }

    fn config_with_run() -> (WebConfig, PathBuf) {
        let root = temporary_directory("route");
        let directory = root.join("Run55_Erudition_EMPTY");
        fs::create_dir_all(&directory).unwrap();
        let scenario = automata_io::Scenario::from_number(55, 42).unwrap();
        let mut manifest = automata_io::Manifest::new(&scenario, 2024, 1, 0.3, 10);
        manifest.set_u64("interactions", 42);
        manifest.save(&directory.join("manifest.txt")).unwrap();
        fs::write(directory.join("report.md"), "# report").unwrap();
        let config = WebConfig {
            data_dir: root.clone(),
            ..WebConfig::default()
        };
        (config, root)
    }

    #[test]
    fn health_and_runs_are_json() {
        let (config, root) = config_with_run();
        let health = route(&config, &request("GET", "/api/health"));
        assert_eq!(health.status, 200);
        assert!(String::from_utf8_lossy(&health.body).contains("\"status\":\"ok\""));

        let runs = route(&config, &request("GET", "/api/runs"));
        assert_eq!(runs.status, 200);
        assert!(String::from_utf8_lossy(&runs.body).contains("Run55_Erudition_EMPTY"));

        let detail = route(&config, &request("GET", "/api/runs/55"));
        assert_eq!(detail.status, 200);
        assert!(String::from_utf8_lossy(&detail.body).contains("\"manifest\""));

        let reports = route(&config, &request("GET", "/api/runs/55/reports"));
        assert_eq!(reports.status, 200);
        assert!(String::from_utf8_lossy(&reports.body).contains("report.md"));

        let file = route(
            &config,
            &request("GET", "/files/runs/Run55_Erudition_EMPTY/report.md"),
        );
        assert_eq!(file.status, 200);
        assert_eq!(file.body, b"# report");

        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn rejects_unknown_runs_and_traversal() {
        let (config, root) = config_with_run();
        assert_eq!(route(&config, &request("GET", "/api/runs/999")).status, 404);
        assert_eq!(
            route(&config, &request("GET", "/files/runs/55/../manifest.txt")).status,
            404
        );
        assert_eq!(
            route(&config, &request("GET", "/plots/../../etc/passwd")).status,
            404
        );
        assert_eq!(route(&config, &request("POST", "/api/runs")).status, 405);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn token_protects_api_but_not_the_dashboard() {
        let (mut config, root) = config_with_run();
        config.token = Some("secret".to_string());
        let mut unauthorized = request("GET", "/api/runs");
        assert!(!authorized(&unauthorized, &config));
        unauthorized
            .headers
            .push(("authorization".to_string(), "Bearer secret".to_string()));
        assert!(authorized(&unauthorized, &config));

        let mut query = request("GET", "/api/runs");
        query.query = Some("token=secret".to_string());
        assert!(authorized(&query, &config));

        assert!(!needs_auth("/"));
        assert!(needs_auth("/api/runs"));
        assert!(needs_auth("/plots/x.png"));
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn static_files_are_served_from_the_web_directory() {
        let root = temporary_directory("static");
        let web = root.join("dist");
        fs::create_dir_all(&web).unwrap();
        fs::write(web.join("index.html"), "<h1>app</h1>").unwrap();
        fs::write(web.join("app.js"), "console.log(1)").unwrap();
        let config = WebConfig {
            web_dir: web,
            ..WebConfig::default()
        };
        let index = route(&config, &request("GET", "/"));
        assert_eq!(index.status, 200);
        assert_eq!(index.content_type, "text/html; charset=utf-8");
        let script = route(&config, &request("GET", "/app.js"));
        assert_eq!(script.content_type, "text/javascript; charset=utf-8");
        assert_eq!(route(&config, &request("GET", "/../secret")).status, 404);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn constant_time_comparison_matches_equality() {
        assert!(constant_time_eq(b"abc", b"abc"));
        assert!(!constant_time_eq(b"abc", b"abd"));
        assert!(!constant_time_eq(b"abc", b"ab"));
    }
}
