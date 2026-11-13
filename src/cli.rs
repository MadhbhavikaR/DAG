//! Minimal command-line interface for configuration validation and health.

use crate::config::Config;
use crate::logging::{self, log};
use crate::VERSION;
use std::path::PathBuf;

/// Execute the CLI using the supplied arguments (excluding argv[0]).
pub fn run<I, S>(arguments: I) -> Result<(), String>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut arguments = arguments.into_iter().map(Into::into);
    let command = arguments.next().unwrap_or_else(|| "help".to_owned());

    match command.as_str() {
        "help" | "--help" | "-h" => {
            print_help();
            Ok(())
        }
        "version" | "--version" | "-V" => {
            println!("dag-nvr-ai {VERSION}");
            Ok(())
        }
        "health" => {
            println!("{{\"status\":\"ok\",\"version\":\"{VERSION}\"}}");
            Ok(())
        }
        "validate-config" => {
            let config_path = parse_config_argument(arguments)?;
            let config = Config::load(config_path.as_deref()).map_err(|error| error.to_string())?;
            logging::init(config.log_level);
            log(
                crate::config::LogLevel::Info,
                "configuration validated successfully",
            );
            println!(
                "configuration valid: host={}, channels={}, queue_capacity={}, inference_concurrency={}",
                config.nvr_host,
                config.nvr_channels,
                config.event_queue_capacity,
                config.max_concurrent_inference
            );
            Ok(())
        }
        _ => Err(format!("unknown command '{command}'. Run 'dag-nvr-ai help'.")),
    }
}

fn parse_config_argument<I>(arguments: I) -> Result<Option<PathBuf>, String>
where
    I: IntoIterator<Item = String>,
{
    let mut path = None;

    for argument in arguments {
        if argument == "--config" {
            return Err(
                "--config requires a path, for example --config=config/dag-nvr-ai.conf"
                    .to_owned(),
            );
        }

        if let Some(value) = argument.strip_prefix("--config=") {
            if value.is_empty() || path.is_some() {
                return Err("--config requires exactly one non-empty path".to_owned());
            }
            path = Some(PathBuf::from(value));
        } else {
            return Err(format!("unknown argument '{argument}'"));
        }
    }

    Ok(path)
}

fn print_help() {
    println!(
        "DAG Nano NVR AI {VERSION}\n\
         Usage:\n\
         dag-nvr-ai help\n\
         dag-nvr-ai version\n\
         dag-nvr-ai health\n\
         dag-nvr-ai validate-config [--config=PATH]\n\n\
         Configuration precedence: defaults < config file < DAG_* environment variables."
    );
}
