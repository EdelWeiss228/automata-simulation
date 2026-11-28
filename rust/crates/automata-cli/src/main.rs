use std::fs;
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Instant;

use automata_core::{
    AgentSpec, ArchetypeKind, Context, Degree, InitMode, Outcome, RunReport, World, WorldConfig,
};
use automata_io::{
    BatchOptions, ClickHouseConfig, RunOptions, Scenario, run as run_scenario_io,
    run_batch as run_batch_io,
};
use automata_university::{University, UniversityConfig};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Command {
    Core,
    University,
    Run,
    Batch,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum OutputFormat {
    KeyValue,
    Csv,
}

#[derive(Debug)]
struct Options {
    command: Command,
    agents: usize,
    days: u32,
    days_set: bool,
    seed: u64,
    threads: usize,
    init: InitMode,
    archetype: Option<ArchetypeKind>,
    context: Context,
    format: OutputFormat,
    start_year: i32,
    master_chance: f32,
    run_number: Option<u16>,
    output_dir: Option<PathBuf>,
    run_numbers: Option<Vec<u16>>,
    snapshot_in: Option<PathBuf>,
    snapshot_out: Option<PathBuf>,
    clickhouse: bool,
    clickhouse_required: bool,
    checkpoint_every: u32,
    fail_fast: bool,
    log_interactions: bool,
    log_states: bool,
    log_relations: bool,
    csv_enabled: bool,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            command: Command::Core,
            agents: 100,
            days: 30,
            days_set: false,
            seed: 42,
            threads: 1,
            init: InitMode::Empty,
            archetype: None,
            context: Context::Study,
            format: OutputFormat::KeyValue,
            start_year: 2024,
            master_chance: 0.3,
            run_number: None,
            output_dir: None,
            run_numbers: None,
            snapshot_in: None,
            snapshot_out: None,
            clickhouse: false,
            clickhouse_required: false,
            checkpoint_every: 30,
            fail_fast: false,
            log_interactions: true,
            log_states: true,
            log_relations: true,
            csv_enabled: true,
        }
    }
}

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
    let options = parse_args()?;

    match options.command {
        Command::Core => run_core(&options),
        Command::University => run_university(&options),
        Command::Run => run_one_scenario(&options),
        Command::Batch => run_batch(&options),
    }
}

fn run_core(options: &Options) -> Result<(), String> {
    let bachelor_count = options.agents.saturating_mul(1500) / 1620;
    let mut specs = Vec::with_capacity(options.agents);
    for index in 0..options.agents {
        let archetype = options
            .archetype
            .unwrap_or(ArchetypeKind::ALL[index % ArchetypeKind::ALL.len()]);
        let sensitivity = 0.1 + ((index * 37) % 290) as f32 / 100.0;
        let group_id = (index / 25) as u32;
        let course_year = ((index % 4) + 1) as u8;
        let degree = if index < bachelor_count {
            Degree::Bachelor
        } else {
            Degree::Master
        };

        specs.push(AgentSpec::new(
            format!("A-{index:04}"),
            archetype,
            sensitivity,
            group_id,
            course_year,
            degree,
        ));
    }

    let config = WorldConfig {
        seed: options.seed,
        parallelism: options.threads,
        init_mode: options.init,
        ..WorldConfig::default()
    };

    let init_start = Instant::now();
    let mut world = World::from_specs(specs, config);
    let init_elapsed = init_start.elapsed();

    let run_start = Instant::now();
    let report: RunReport = world.run(options.days, options.context);
    let run_elapsed = run_start.elapsed();

    let archetype = options.archetype.map_or("mixed", ArchetypeKind::name);
    let init_ms = init_elapsed.as_secs_f64() * 1000.0;
    let sim_ms = run_elapsed.as_secs_f64() * 1000.0;

    match options.format {
        OutputFormat::KeyValue => {
            println!("model=automata-core/0.1.0");
            println!("seed={}", options.seed);
            println!("agents={}", options.agents);
            println!("days={}", report.days);
            println!("threads={}", options.threads);
            println!("init={:?}", options.init);
            println!("archetype={archetype}");
            println!("context={}", options.context.key());
            println!("init_ms={init_ms:.3}");
            println!("sim_ms={sim_ms:.3}");
            println!("interactions={}", report.total_interactions);
            println!("success={}", report.successes);
            println!("failure={}", report.failures);
            println!("refusal={}", report.refusals);
            println!("final_hash=0x{:016x}", report.final_hash);
            println!("final_rng_state=0x{:016x}", report.final_rng_state);
        }
        OutputFormat::Csv => {
            println!(
                "model,seed,agents,days,threads,init,archetype,context,init_ms,sim_ms,interactions,success,failure,refusal,final_hash,final_rng_state"
            );
            println!(
                "automata-core/0.1.0,{},{},{},{},{:?},{},{},{:.3},{:.3},{},{},{},{},0x{:016x},0x{:016x}",
                options.seed,
                options.agents,
                report.days,
                options.threads,
                options.init,
                archetype,
                options.context.key(),
                init_ms,
                sim_ms,
                report.total_interactions,
                report.successes,
                report.failures,
                report.refusals,
                report.final_hash,
                report.final_rng_state
            );
        }
    }

    Ok(())
}

#[derive(Default)]
struct UniversitySummary {
    days: u32,
    sundays: u32,
    rotations: u32,
    interactions: u64,
    successes: u64,
    failures: u64,
    refusals: u64,
}

fn run_university(options: &Options) -> Result<(), String> {
    let config = UniversityConfig {
        seed: options.seed,
        start_year: options.start_year,
        parallelism: options.threads,
        init_mode: options.init,
        master_chance: options.master_chance,
        ..UniversityConfig::default()
    };

    let init_start = Instant::now();
    let mut university = if let Some(path) = &options.snapshot_in {
        let bytes = fs::read(path)
            .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
        University::from_snapshot(&bytes)
            .map_err(|error| format!("failed to load {}: {error}", path.display()))?
    } else {
        University::new(config)
    };
    let init_elapsed = init_start.elapsed();
    let start_day = university.days_completed();

    let run_start = Instant::now();
    let mut summary = UniversitySummary::default();
    while summary.days < options.days {
        let Some(day) = university.step_day() else {
            break;
        };
        summary.days += 1;
        summary.sundays += u32::from(day.is_sunday);
        summary.rotations += u32::from(day.rotation.is_some());
        summary.interactions += day.interactions.len() as u64;
        for event in &day.interactions {
            match event.outcome {
                Outcome::Success => summary.successes += 1,
                Outcome::Failure => summary.failures += 1,
                Outcome::Refusal => summary.refusals += 1,
            }
        }
    }
    let run_elapsed = run_start.elapsed();

    let init_ms = init_elapsed.as_secs_f64() * 1000.0;
    let sim_ms = run_elapsed.as_secs_f64() * 1000.0;
    let final_hash = university.state_hash();
    let final_rng_state = university.rng.state();
    let total_days = university.days_completed();

    if let Some(path) = &options.snapshot_out {
        let bytes = university.to_snapshot();
        fs::write(path, &bytes)
            .map_err(|error| format!("failed to write {}: {error}", path.display()))?;
    }

    match options.format {
        OutputFormat::KeyValue => {
            println!("model=automata-university/0.1.0");
            println!("seed={}", options.seed);
            println!("year={}", options.start_year);
            println!("agents={}", university.len());
            println!("bachelors={}", university.population.bachelors());
            println!("masters={}", university.population.masters());
            println!("start_day={start_day}");
            println!("total_days={total_days}");
            println!("days={}", summary.days);
            println!("sundays={}", summary.sundays);
            println!("rotations={}", summary.rotations);
            println!("threads={}", options.threads);
            println!("init={:?}", options.init);
            println!("master_chance={:.4}", options.master_chance);
            println!("init_ms={init_ms:.3}");
            println!("sim_ms={sim_ms:.3}");
            println!("interactions={}", summary.interactions);
            println!("success={}", summary.successes);
            println!("failure={}", summary.failures);
            println!("refusal={}", summary.refusals);
            println!("final_hash=0x{final_hash:016x}");
            println!("final_rng_state=0x{final_rng_state:016x}");
        }
        OutputFormat::Csv => {
            println!(
                "model,seed,year,agents,bachelors,masters,days,sundays,rotations,threads,init,master_chance,init_ms,sim_ms,interactions,success,failure,refusal,final_hash,final_rng_state"
            );
            println!(
                "automata-university/0.1.0,{},{},{},{},{},{},{},{},{},{:?},{:.4},{:.3},{:.3},{},{},{},{},0x{:016x},0x{:016x}",
                options.seed,
                options.start_year,
                university.len(),
                university.population.bachelors(),
                university.population.masters(),
                summary.days,
                summary.sundays,
                summary.rotations,
                options.threads,
                options.init,
                options.master_chance,
                init_ms,
                sim_ms,
                summary.interactions,
                summary.successes,
                summary.failures,
                summary.refusals,
                final_hash,
                final_rng_state
            );
        }
    }

    Ok(())
}

fn run_one_scenario(options: &Options) -> Result<(), String> {
    let number = options
        .run_number
        .ok_or_else(|| "run mode requires --run-number 55..108".to_string())?;
    let scenario = Scenario::from_number(number, options.seed)
        .ok_or_else(|| format!("--run-number {number} is outside the reserved 55..108 range"))?;
    let output_dir = options
        .output_dir
        .as_ref()
        .ok_or_else(|| "run mode requires --output-dir".to_string())?;

    let mut run_options = RunOptions::new(scenario, output_dir);
    run_options.days = options.days;
    run_options.start_year = options.start_year;
    run_options.parallelism = options.threads;
    run_options.master_chance = options.master_chance;
    run_options.checkpoint_every = options.checkpoint_every;
    run_options.verbose = true;
    run_options.log_interactions = options.log_interactions;
    run_options.log_states = options.log_states;
    run_options.log_relations = options.log_relations;
    run_options.csv_enabled = options.csv_enabled;
    if options.clickhouse || options.clickhouse_required {
        run_options.clickhouse = Some(ClickHouseConfig::from_env());
    }
    run_options.clickhouse_required = options.clickhouse_required;

    let outcome = run_scenario_io(&run_options).map_err(|error| error.to_string())?;
    print_run_outcome(&outcome);
    Ok(())
}

fn run_batch(options: &Options) -> Result<(), String> {
    let output_dir = options
        .output_dir
        .as_ref()
        .ok_or_else(|| "batch mode requires --output-dir".to_string())?;

    let mut batch = BatchOptions::new(output_dir, options.seed);
    batch.days = options.days;
    batch.start_year = options.start_year;
    batch.parallelism = options.threads;
    batch.master_chance = options.master_chance;
    batch.checkpoint_every = options.checkpoint_every;
    batch.fail_fast = options.fail_fast;
    batch.verbose = true;
    batch.log_interactions = options.log_interactions;
    batch.log_states = options.log_states;
    batch.log_relations = options.log_relations;
    batch.csv_enabled = options.csv_enabled;
    batch.run_numbers = options.run_numbers.clone();
    if options.clickhouse || options.clickhouse_required {
        batch.clickhouse = Some(ClickHouseConfig::from_env());
    }
    batch.clickhouse_required = options.clickhouse_required;

    let outcome = run_batch_io(&batch).map_err(|error| error.to_string())?;
    println!("model=automata-batch/0.1.0");
    println!("root={}", output_dir.display());
    println!("completed_this_run={}", outcome.completed_this_run());
    println!("completed_total={}", outcome.completed_total());
    println!("skipped={}", outcome.skipped.len());
    println!("failed={}", outcome.failed.len());
    println!("interactions={}", outcome.total_interactions());
    println!("wall_seconds={:.3}", outcome.wall_seconds);
    for (number, message) in &outcome.failed {
        eprintln!("run {number}: {message}");
    }
    Ok(())
}

fn print_run_outcome(outcome: &automata_io::RunOutcome) {
    println!("model=automata-runner/0.1.0");
    println!("scenario={}", outcome.scenario_name);
    println!("run_id={}", outcome.run_id);
    println!("resumed={}", outcome.resumed);
    println!("completed={}", outcome.completed);
    println!("days={}", outcome.days_completed);
    println!("rotations={}", outcome.rotations);
    println!("semesters={}", outcome.semesters);
    println!("interactions={}", outcome.interactions);
    println!("success={}", outcome.successes);
    println!("failure={}", outcome.failures);
    println!("refusal={}", outcome.refusals);
    println!("final_hash=0x{:016x}", outcome.final_hash);
    println!("wall_seconds={:.3}", outcome.wall_seconds);
}

fn parse_args() -> Result<Options, String> {
    let mut options = Options::default();
    let mut raw: Vec<String> = std::env::args().skip(1).collect();

    if let Some(first) = raw.first() {
        match first.to_lowercase().as_str() {
            "core" | "prototype" => {
                options.command = Command::Core;
                raw.remove(0);
            }
            "university" | "uni" => {
                options.command = Command::University;
                raw.remove(0);
            }
            "run" | "scenario" => {
                options.command = Command::Run;
                raw.remove(0);
            }
            "batch" | "matrix" => {
                options.command = Command::Batch;
                raw.remove(0);
            }
            _ => {}
        }
    }

    let mut args = raw.into_iter();
    let mut init_set = false;

    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--help" | "-h" => {
                print_usage();
                std::process::exit(0);
            }
            "--agents" => {
                options.agents = parse_usize(args.next(), "--agents")?;
            }
            "--days" => {
                options.days = parse_u32(args.next(), "--days")?;
                options.days_set = true;
            }
            "--seed" => {
                options.seed = parse_u64(args.next(), "--seed")?;
            }
            "--threads" => {
                options.threads = parse_usize(args.next(), "--threads")?.max(1);
            }
            "--init" => {
                options.init = parse_init(args.next())?;
                init_set = true;
            }
            "--archetype" => {
                options.archetype = parse_archetype(args.next())?;
            }
            "--context" => {
                options.context = parse_context(args.next())?;
            }
            "--format" => {
                options.format = parse_format(args.next())?;
            }
            "--year" => {
                options.start_year = parse_i32(args.next(), "--year")?;
            }
            "--master-chance" => {
                options.master_chance = parse_f32(args.next(), "--master-chance")?;
            }
            "--run-number" => {
                options.run_number = Some(parse_u16(args.next(), "--run-number")?);
            }
            "--run-numbers" => {
                options.run_numbers = Some(parse_run_numbers(args.next())?);
            }
            "--output-dir" => {
                options.output_dir =
                    Some(PathBuf::from(args.next().ok_or_else(|| {
                        "--output-dir requires a value".to_string()
                    })?));
            }
            "--snapshot-in" => {
                options.snapshot_in =
                    Some(PathBuf::from(args.next().ok_or_else(|| {
                        "--snapshot-in requires a value".to_string()
                    })?));
            }
            "--snapshot-out" => {
                options.snapshot_out =
                    Some(PathBuf::from(args.next().ok_or_else(|| {
                        "--snapshot-out requires a value".to_string()
                    })?));
            }
            "--checkpoint-every" => {
                options.checkpoint_every = parse_u32(args.next(), "--checkpoint-every")?;
            }
            "--clickhouse" => {
                options.clickhouse = true;
            }
            "--clickhouse-required" => {
                options.clickhouse = true;
                options.clickhouse_required = true;
            }
            "--fail-fast" => {
                options.fail_fast = true;
            }
            "--no-interactions" => {
                options.log_interactions = false;
            }
            "--no-states" => {
                options.log_states = false;
            }
            "--no-relations" => {
                options.log_relations = false;
            }
            "--no-csv" => {
                options.csv_enabled = false;
            }
            other => return Err(format!("unknown argument: {other}")),
        }
    }

    match options.command {
        Command::University => {
            if !init_set {
                options.init = InitMode::Mixed;
            }
            if options.run_number.is_some()
                || options.output_dir.is_some()
                || options.run_numbers.is_some()
            {
                return Err("run/batch arguments are not valid in university mode".to_string());
            }
        }
        Command::Run => {
            if options.snapshot_in.is_some() || options.snapshot_out.is_some() {
                return Err(
                    "use the run manifest for snapshots; --snapshot-in/out belong to university mode"
                        .to_string(),
                );
            }
            if options.run_number.is_none() {
                return Err("run mode requires --run-number".to_string());
            }
            if options.output_dir.is_none() {
                return Err("run mode requires --output-dir".to_string());
            }
            if options.run_numbers.is_some() {
                return Err("--run-numbers is only valid in batch mode".to_string());
            }
            if !options.days_set {
                options.days = automata_io::DEFAULT_DAYS_TOTAL;
            }
        }
        Command::Batch => {
            if options.snapshot_in.is_some() || options.snapshot_out.is_some() {
                return Err(
                    "use the run manifest for snapshots; --snapshot-in/out belong to university mode"
                        .to_string(),
                );
            }
            if options.output_dir.is_none() {
                return Err("batch mode requires --output-dir".to_string());
            }
            if options.run_number.is_some() {
                return Err("--run-number is only valid in run mode".to_string());
            }
            if !options.days_set {
                options.days = automata_io::DEFAULT_DAYS_TOTAL;
            }
        }
        Command::Core => {}
    }

    if options.command != Command::University
        && (options.snapshot_in.is_some() || options.snapshot_out.is_some())
    {
        return Err("--snapshot-in/out are only valid in university mode".to_string());
    }
    if options.agents == 0 {
        return Err("--agents must be positive".to_string());
    }
    if options.days == 0 {
        return Err("--days must be positive".to_string());
    }
    if !(0.0..=1.0).contains(&options.master_chance) {
        return Err("--master-chance must be in [0, 1]".to_string());
    }
    if (options.command == Command::Run || options.command == Command::Batch)
        && options.checkpoint_every == 0
    {
        return Err("--checkpoint-every must be positive for resumable runs".to_string());
    }

    Ok(options)
}

fn parse_i32(value: Option<String>, name: &str) -> Result<i32, String> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be an integer"))
}

fn parse_f32(value: Option<String>, name: &str) -> Result<f32, String> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be a number"))
}

fn parse_usize(value: Option<String>, name: &str) -> Result<usize, String> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be a non-negative integer"))
}

fn parse_u32(value: Option<String>, name: &str) -> Result<u32, String> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be a non-negative integer"))
}

fn parse_u16(value: Option<String>, name: &str) -> Result<u16, String> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be a non-negative integer"))
}

fn parse_run_numbers(value: Option<String>) -> Result<Vec<u16>, String> {
    let value = value.ok_or_else(|| "--run-numbers requires a value".to_string())?;
    let mut numbers = Vec::new();
    for part in value.split(',') {
        let part = part.trim();
        if part.is_empty() {
            continue;
        }
        numbers.push(
            part.parse()
                .map_err(|_| format!("invalid run number: {part}"))?,
        );
    }
    if numbers.is_empty() {
        return Err("--run-numbers must contain at least one number".to_string());
    }
    Ok(numbers)
}

fn parse_u64(value: Option<String>, name: &str) -> Result<u64, String> {
    value
        .ok_or_else(|| format!("{name} requires a value"))?
        .parse()
        .map_err(|_| format!("{name} must be a non-negative integer"))
}

fn parse_init(value: Option<String>) -> Result<InitMode, String> {
    let value = value.ok_or_else(|| "--init requires a value".to_string())?;
    match value.to_lowercase().as_str() {
        "empty" => Ok(InitMode::Empty),
        "random" => Ok(InitMode::Random),
        "mixed" => Ok(InitMode::Mixed),
        other => Err(format!(
            "--init must be empty, random or mixed, got {other}"
        )),
    }
}

fn parse_context(value: Option<String>) -> Result<Context, String> {
    let value = value.ok_or_else(|| "--context requires a value".to_string())?;
    match value.to_lowercase().as_str() {
        "study" => Ok(Context::Study),
        "break" => Ok(Context::Break),
        "gym" => Ok(Context::Gym),
        other => Err(format!(
            "--context must be study, break or gym, got {other}"
        )),
    }
}

fn parse_format(value: Option<String>) -> Result<OutputFormat, String> {
    let value = value.ok_or_else(|| "--format requires a value".to_string())?;
    match value.to_lowercase().as_str() {
        "kv" | "keyvalue" | "text" => Ok(OutputFormat::KeyValue),
        "csv" => Ok(OutputFormat::Csv),
        other => Err(format!("--format must be keyvalue or csv, got {other}")),
    }
}

fn parse_archetype(value: Option<String>) -> Result<Option<ArchetypeKind>, String> {
    let value = value.ok_or_else(|| "--archetype requires a value".to_string())?;
    if value.eq_ignore_ascii_case("mixed") || value.eq_ignore_ascii_case("all") {
        return Ok(None);
    }
    ArchetypeKind::from_name(&value)
        .map(Some)
        .ok_or_else(|| format!("unknown archetype: {value}"))
}

fn print_usage() {
    println!(
        "automata-cli — deterministic v3 runner\n\
         \n\
         Usage:\n\
           cargo run --release -p automata-cli -- core [options]\n\
           cargo run --release -p automata-cli -- university [options]\n\
           cargo run --release -p automata-cli -- run --run-number <55..108> --output-dir <dir> [options]\n\
           cargo run --release -p automata-cli -- batch --output-dir <dir> [options]\n\
         \n\
         Common options:\n\
           --days <n>            simulated days (core default 30; run/batch default 1213)\n\
           --seed <n>            RNG seed (default 42)\n\
           --threads <n>         worker threads for independent phases (default 1)\n\
           --year <yyyy>         university start year (default 2024)\n\
           --master-chance <p>   share of bachelors continuing to a master (default 0.3)\n\
           --format <name>       keyvalue | csv (default keyvalue)\n\
           --help                print this help\n\
         \n\
         Core/university options:\n\
           --agents <n>          number of prototype agents (default 100)\n\
           --init <mode>         empty | random | mixed (default empty; university: mixed)\n\
           --archetype <name>    prototype archetype, or mixed (default mixed)\n\
           --context <name>      prototype context: study | break | gym (default study)\n\
           --snapshot-in <path>  continue a university snapshot\n\
           --snapshot-out <path> write a university snapshot after the run\n\
         \n\
         Run/batch options:\n\
           --run-number <n>      one reserved v3 scenario (55..108)\n\
           --run-numbers <list>  comma-separated subset for batch mode\n\
           --output-dir <dir>    run directory or batch root (required)\n\
           --checkpoint-every <n> snapshot interval in days (default 30)\n\
           --clickhouse          write CSV and ClickHouse (credentials from CLICKHOUSE_*)\n\
           --clickhouse-required fail instead of falling back to CSV-only\n\
           --fail-fast           stop the batch at the first failed run\n\
           --no-interactions     skip the interactions CSV/table\n\
           --no-states           skip the daily emotion CSV/table\n\
           --no-relations        skip the daily relation CSV/table\n\
           --no-csv              ClickHouse-only run (no CSV mirror)\n\
         \n\
         Key-value output is stable text suitable for a benchmark script.\n\
         CSV output is directly appendable to a machine-readable timings table."
    );
}
