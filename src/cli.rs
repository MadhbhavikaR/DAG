//! Command-line interface for configuration, health and NVR discovery.

use crate::config::{Config, LogLevel};
use crate::logging::{self, log};
use crate::nvr::client::HikvisionIsapiClient;
use crate::nvr::credentials::NvrCredentials;
use crate::VERSION;
use std::path::PathBuf;
use std::sync::atomic::AtomicBool;

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
            log(LogLevel::Info, "configuration validated successfully");
            println!(
                "configuration valid: host={}, channels={}, queue_capacity={}, inference_concurrency={}",
                config.nvr_host,
                config.nvr_channels,
                config.event_queue_capacity,
                config.max_concurrent_inference
            );
            Ok(())
        }
        "probe-nvr" => {
            let config_path = parse_config_argument(arguments)?;
            let config = Config::load(config_path.as_deref()).map_err(|error| error.to_string())?;
            logging::init(config.log_level);
            let credentials = NvrCredentials::from_env().map_err(|error| error.to_string())?;
            let client = HikvisionIsapiClient::new(&config, credentials);
            let (curl_version, device) = client.probe().map_err(|error| error.to_string())?;
            println!("NVR connectivity: OK");
            println!("curl: {curl_version}");
            println!("model: {}", device.model);
            println!("firmware: {}", device.firmware_version);
            println!("firmware build: {}", device.firmware_build);
            println!("device name: {}", device.device_name);
            Ok(())
        }
        "listen-events" => {
            let config_path = parse_config_argument(arguments)?;
            let config = Config::load(config_path.as_deref()).map_err(|error| error.to_string())?;
            logging::init(config.log_level);
            let credentials = NvrCredentials::from_env().map_err(|error| error.to_string())?;
            let client = HikvisionIsapiClient::new(&config, credentials);
            let stop = AtomicBool::new(false);
            log(LogLevel::Info, "listening for active NVR motion events");
            client
                .listen(&stop, |event| {
                    log(
                        LogLevel::Info,
                        &format!(
                            "motion event: channel={} type={} timestamp={}",
                            event.channel_id, event.event_type, event.timestamp
                        ),
                    );
                })
                .map_err(|error| error.to_string())
        }
        _ => Err(format!(
            "unknown command '{command}'. Run 'dag-nvr-ai help'."
        )),
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
                "--config requires a path, for example --config=config/dag-nvr-ai.conf".to_owned(),
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
         dag-nvr-ai validate-config [--config=PATH]\n\
         dag-nvr-ai probe-nvr [--config=PATH]\n\
         dag-nvr-ai listen-events [--config=PATH]\n\n\
         NVR credentials are read only from DAG_NVR_USERNAME and DAG_NVR_PASSWORD.\n\
         Configuration precedence: defaults < config file < DAG_* environment variables."
    );
}
