use std::process::ExitCode;
use std::time::Instant;

use automata_core::{
    AgentSpec, ArchetypeKind, Context, Degree, InitMode, Outcome, RunReport, World, WorldConfig,
};
use automata_university::{University, UniversityConfig};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum WorldKind {
    Core,
    University,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum OutputFormat {
    KeyValue,
    Csv,
}

#[derive(Debug)]
struct Options {
    world: WorldKind,
    agents: usize,
    days: u32,
    seed: u64,
    threads: usize,
    init: InitMode,
    archetype: Option<ArchetypeKind>,
    context: Context,
    format: OutputFormat,
    start_year: i32,
    master_chance: f32,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            world: WorldKind::Core,
            agents: 100,
            days: 30,
            seed: 42,
            threads: 1,
            init: InitMode::Empty,
            archetype: None,
            context: Context::Study,
            format: OutputFormat::KeyValue,
            start_year: 2024,
            master_chance: 0.3,
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

    match options.world {
        WorldKind::Core => run_core(&options),
        WorldKind::University => run_university(&options),
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
    let mut university = University::new(config);
    let init_elapsed = init_start.elapsed();

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

    match options.format {
        OutputFormat::KeyValue => {
            println!("model=automata-university/0.1.0");
            println!("seed={}", options.seed);
            println!("year={}", options.start_year);
            println!("agents={}", university.len());
            println!("bachelors={}", university.population.bachelors());
            println!("masters={}", university.population.masters());
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

fn parse_args() -> Result<Options, String> {
    let mut options = Options::default();
    let mut raw: Vec<String> = std::env::args().skip(1).collect();

    if let Some(first) = raw.first() {
        match first.to_lowercase().as_str() {
            "core" | "prototype" => {
                options.world = WorldKind::Core;
                raw.remove(0);
            }
            "university" | "uni" => {
                options.world = WorldKind::University;
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
            other => return Err(format!("unknown argument: {other}")),
        }
    }

    if options.world == WorldKind::University && !init_set {
        options.init = InitMode::Mixed;
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
           cargo run --release -p automata-cli -- [core|university] [options]\n\
         \n\
         Options:\n\
           --agents <n>          number of prototype agents (default 100)\n\
           --days <n>            simulated days (default 30; university horizon 1213)\n\
           --seed <n>            RNG seed (default 42)\n\
           --threads <n>         worker threads for independent phases (default 1)\n\
           --init <mode>         empty | random | mixed (default empty; university: mixed)\n\
           --archetype <name>    prototype archetype, or mixed (default mixed)\n\
           --context <name>      prototype context: study | break | gym (default study)\n\
           --year <yyyy>         university start year (default 2024)\n\
           --master-chance <p>   share of bachelors continuing to a master (default 0.3)\n\
           --format <name>       keyvalue | csv (default keyvalue)\n\
           --help                print this help\n\
         \n\
         Key-value output is stable text suitable for a benchmark script.\n\
         CSV output is directly appendable to a machine-readable timings table."
    );
}
