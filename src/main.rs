//! Command-line entry point.

use std::process::ExitCode;

fn main() -> ExitCode {
    match dag_nvr_ai::cli::run(std::env::args().skip(1)) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::from(2)
        }
    }
}
