use std::path::PathBuf;
use std::process::ExitCode;

use automata_web::{WebConfig, serve};

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("error: {message}");
            eprintln!();
            print_usage();
            ExitCode::from(2)
        }
    }
}

fn run() -> Result<(), String> {
    let mut config = WebConfig::from_env();
    let mut args = std::env::args().skip(1);
    while let Some(argument) = args.next() {
        match argument.as_str() {
            "--bind" => config.bind = value(args.next(), "--bind")?,
            "--data-dir" => config.data_dir = PathBuf::from(value(args.next(), "--data-dir")?),
            "--plots-dir" => config.plots_dir = PathBuf::from(value(args.next(), "--plots-dir")?),
            "--web-dir" => config.web_dir = PathBuf::from(value(args.next(), "--web-dir")?),
            "--help" | "-h" => {
                print_usage();
                return Ok(());
            }
            other => return Err(format!("unknown argument: {other}")),
        }
    }
    serve(config).map_err(|error| error.to_string())
}

fn value(value: Option<String>, name: &str) -> Result<String, String> {
    value.ok_or_else(|| format!("{name} requires a value"))
}

fn print_usage() {
    println!(
        "\
automata-web {version}

Read-only HTTP/JSON API and dashboard for v3 runs.

Usage:
  cargo run --release -p automata-web -- [options]

Options:
  --bind <addr>        listen address (default 127.0.0.1:8080)
  --data-dir <path>    batch root with run directories (default data/v3)
  --plots-dir <path>   static plots directory (default data/plots)
  --web-dir <path>     built SPA directory (default web/dist)
  --help               print this help

Environment:
  AUTOMATA_WEB_BIND, AUTOMATA_DATA_DIR, AUTOMATA_PLOTS_DIR,
  AUTOMATA_WEB_DIR, AUTOMATA_WEB_TOKEN

Endpoints:
  GET /api/health
  GET /api/runs
  GET /api/runs/<number|run_id|directory>
  GET /api/runs/<key>/reports
  GET /api/events                (SSE progress stream)
  GET /files/runs/<key>/<file>   (report files)
  GET /plots/<file>
  GET /                          (web/dist or the built-in dashboard)

If AUTOMATA_WEB_TOKEN is set, /api, /files and /plots require
`Authorization: Bearer <token>`, `X-Automata-Token`, or `?token=`.
The dashboard is public so it can ask for the token.",
        version = env!("CARGO_PKG_VERSION")
    );
}
