//! Versioned binary snapshots for resumable university runs.
//!
//! The format is intentionally small and dependency-free.  It stores the
//! authoritative population, the nonzero relation edges, both RNG streams and
//! the schedule book; the dense zero relation matrix, statuses and derived
//! vectors are rebuilt on load.  A snapshot is taken at a day boundary, after
//! `CLEANUP`, so the next day starts from the same state as an uninterrupted
//! run.

use std::fmt;

use automata_core::{
    ArchetypeKind, Degree, EmotionAxis, EmotionVector, InitMode, Relation, World, WorldConfig,
};

use crate::calendar::Calendar;
use crate::campus::Campus;
use crate::population::{GroupRegistry, Population, PopulationConfig, RotationReport, Student};
use crate::schedule::{PAIRS_PER_DAY, ScheduleBook, WEEKDAYS, WeekSchedule};

use super::{University, UniversityConfig};

pub const SNAPSHOT_MAGIC: [u8; 8] = *b"AUTOV3U1";
pub const SNAPSHOT_VERSION: u32 = 1;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SnapshotError {
    InvalidMagic,
    UnsupportedVersion(u32),
    UnexpectedEof { offset: usize },
    InvalidData(String),
}

impl fmt::Display for SnapshotError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidMagic => formatter.write_str("not an automata v3 university snapshot"),
            Self::UnsupportedVersion(version) => {
                write!(formatter, "unsupported snapshot version {version}")
            }
            Self::UnexpectedEof { offset } => {
                write!(formatter, "unexpected end of snapshot at byte {offset}")
            }
            Self::InvalidData(message) => write!(formatter, "invalid snapshot data: {message}"),
        }
    }
}

impl std::error::Error for SnapshotError {}

impl University {
    /// Serializes the persistent state.  Derived vectors (`statuses`,
    /// `sportiness`, ...) are intentionally not stored: `begin_day` resets
    /// them and `sync_university_state` rebuilds them from the population.
    pub fn to_snapshot(&self) -> Vec<u8> {
        let mut writer = Writer::default();
        writer.bytes(&SNAPSHOT_MAGIC);
        writer.u32(SNAPSHOT_VERSION);
        write_university_config(&mut writer, &self.config);
        write_population_config(&mut writer, self.population.config());

        writer.u64(self.population.rng_state());
        writer.i32(self.population.current_year);
        let (bachelor_weights, master_weights) = self.population.rotation_weights();
        write_weights(&mut writer, bachelor_weights);
        write_weights(&mut writer, master_weights);

        writer.u32(self.population.groups.len() as u32);
        for (name, id) in self.population.groups.iter() {
            writer.string(name);
            writer.u32(id);
        }

        writer.u32(self.population.students.len() as u32);
        for student in &self.population.students {
            write_student(&mut writer, student);
        }

        write_world_config(&mut writer, &self.world.config);
        writer.u64(self.world.rng.state());
        writer.u32(self.world.day);

        let mut edges = 0u32;
        for from in 0..self.world.len() {
            for to in 0..self.world.len() {
                if !self.world.relations[from * self.world.len() + to].is_zero() {
                    edges += 1;
                }
            }
        }
        writer.u32(edges);
        for from in 0..self.world.len() {
            for to in 0..self.world.len() {
                let relation = self.world.relations[from * self.world.len() + to];
                if relation.is_zero() {
                    continue;
                }
                writer.u32(from as u32);
                writer.u32(to as u32);
                for axis in automata_core::RelationAxis::ALL {
                    writer.i16(relation.get(axis));
                }
            }
        }

        writer.u32(self.world.agents.len() as u32);
        for agent in &self.world.agents {
            for axis in EmotionAxis::ALL {
                writer.i16(agent.emotions.get(axis).get());
            }
        }

        writer.u32(self.schedules.len() as u32);
        for (group, schedule) in self.schedules.entries() {
            writer.string(group);
            for weekday in 0..WEEKDAYS {
                for pair in 0..PAIRS_PER_DAY {
                    match schedule.pair(weekday, pair) {
                        Some(room) => {
                            writer.u8(1);
                            writer.string(room);
                        }
                        None => writer.u8(0),
                    }
                }
            }
        }

        writer.u64(self.rng.state());
        writer.u32(self.days_completed);
        writer.u32(self.rotations.len() as u32);
        for report in &self.rotations {
            write_rotation(&mut writer, report);
        }

        writer.finish()
    }

    /// Restores a snapshot.  The calendar is replayed from the start year and
    /// `days_completed`, which keeps the checkpoint independent of private
    /// calendar fields.
    pub fn from_snapshot(bytes: &[u8]) -> Result<Self, SnapshotError> {
        let mut reader = Reader::new(bytes);
        if reader.bytes(8)? != SNAPSHOT_MAGIC {
            return Err(SnapshotError::InvalidMagic);
        }
        let version = reader.u32()?;
        if version != SNAPSHOT_VERSION {
            return Err(SnapshotError::UnsupportedVersion(version));
        }

        let config = read_university_config(&mut reader)?;
        let population_config = read_population_config(&mut reader)?;
        let population_rng = reader.u64()?;
        let current_year = reader.i32()?;
        let bachelor_weights = read_weights(&mut reader)?;
        let master_weights = read_weights(&mut reader)?;

        let group_count = reader.count(1_000_000)?;
        let mut groups = Vec::with_capacity(group_count);
        for _ in 0..group_count {
            let name = reader.string()?;
            let id = reader.u32()?;
            groups.push((name, id));
        }

        let student_count = reader.count(1_000_000)?;
        let mut students = Vec::with_capacity(student_count);
        for _ in 0..student_count {
            students.push(read_student(&mut reader)?);
        }

        let world_config = read_world_config(&mut reader)?;
        let world_rng = reader.u64()?;
        let world_day = reader.u32()?;

        let edge_count = reader.count(50_000_000)?;
        let mut relations = Vec::with_capacity(edge_count);
        for _ in 0..edge_count {
            let from = reader.u32()? as usize;
            let to = reader.u32()? as usize;
            let utility = reader.i16()?;
            let affinity = reader.i16()?;
            let trust = reader.i16()?;
            relations.push((from, to, Relation::new(utility, affinity, trust)));
        }

        let emotion_count = reader.count(1_000_000)?;
        let mut emotions = Vec::with_capacity(emotion_count);
        for _ in 0..emotion_count {
            let mut vector = EmotionVector::default();
            for axis in EmotionAxis::ALL {
                vector.set(axis, reader.i16()?);
            }
            emotions.push(vector);
        }

        let schedule_count = reader.count(1_000_000)?;
        let mut schedules = ScheduleBook::new();
        for _ in 0..schedule_count {
            let group = reader.string()?;
            let mut schedule = WeekSchedule::empty();
            for weekday in 0..WEEKDAYS {
                for pair in 0..PAIRS_PER_DAY {
                    let room = match reader.u8()? {
                        0 => None,
                        1 => Some(reader.string()?),
                        other => {
                            return Err(SnapshotError::InvalidData(format!(
                                "room flag must be 0 or 1, got {other}"
                            )));
                        }
                    };
                    schedule.set_pair(weekday, pair, room);
                }
            }
            schedules.insert(group, schedule);
        }

        let university_rng = reader.u64()?;
        let days_completed = reader.u32()?;
        let rotation_count = reader.count(1_000_000)?;
        let mut rotations = Vec::with_capacity(rotation_count);
        for _ in 0..rotation_count {
            rotations.push(read_rotation(&mut reader)?);
        }
        if !reader.is_empty() {
            return Err(SnapshotError::InvalidData(
                "trailing bytes after snapshot".to_string(),
            ));
        }

        let population = Population::from_snapshot_parts(
            students,
            GroupRegistry::from_entries(groups),
            current_year,
            population_config,
            population_rng,
            bachelor_weights,
            master_weights,
        );

        let n = population.students.len();
        if emotion_count != n {
            return Err(SnapshotError::InvalidData(format!(
                "snapshot has {emotion_count} emotion rows for {n} students"
            )));
        }
        // Relations are restored explicitly below; using Mixed/Random here
        // would consume the world RNG and add edges that are not in the
        // checkpoint.
        let mut build_config = world_config.clone();
        build_config.init_mode = InitMode::Empty;
        let mut world = World::from_specs(population.to_specs(), build_config);
        if world.len() != n {
            return Err(SnapshotError::InvalidData(
                "population and world sizes differ".to_string(),
            ));
        }
        for (agent, emotions) in world.agents.iter_mut().zip(emotions.iter()) {
            agent.emotions = *emotions;
        }
        world.relations.fill(Relation::ZERO);
        for (from, to, relation) in relations {
            if from >= n || to >= n {
                return Err(SnapshotError::InvalidData(format!(
                    "relation edge ({from}, {to}) is outside the {n}-agent world"
                )));
            }
            world.relations[from * n + to] = relation;
        }
        world.config = world_config;
        world.rng = automata_core::DeterministicRng::new(world_rng);
        world.day = world_day;

        let mut calendar = Calendar::new(config.start_year);
        let mut last_day = None;
        for _ in 0..days_completed {
            last_day = calendar.next_day();
        }
        if last_day.is_none() && days_completed > 0 {
            return Err(SnapshotError::InvalidData(format!(
                "calendar ended before day {days_completed}"
            )));
        }

        let mut university = Self {
            world,
            population,
            campus: Campus::new(config.start_year),
            schedules,
            calendar,
            config,
            rng: automata_core::DeterministicRng::new(university_rng),
            current_rooms: Default::default(),
            rotations,
            statuses: Vec::new(),
            arrived_today: Vec::new(),
            left_campus_today: Vec::new(),
            gym_sections: Vec::new(),
            sportiness: Vec::new(),
            skip_tendency: Vec::new(),
            last_day,
            days_completed,
        };
        university.sync_university_state();
        Ok(university)
    }
}

fn write_weights(writer: &mut Writer, weights: [u32; 9]) {
    for weight in weights {
        writer.u32(weight);
    }
}

fn read_weights(reader: &mut Reader<'_>) -> Result<[u32; 9], SnapshotError> {
    let mut weights = [0u32; 9];
    for weight in &mut weights {
        *weight = reader.u32()?;
    }
    Ok(weights)
}

fn write_university_config(writer: &mut Writer, config: &UniversityConfig) {
    writer.u64(config.seed);
    writer.i32(config.start_year);
    writer.u64(config.parallelism as u64);
    writer.u8(init_mode_id(config.init_mode));
    writer.f32(config.master_chance);
    write_weights(writer, config.bachelor_weights);
    write_weights(writer, config.master_weights);
}

fn read_university_config(reader: &mut Reader<'_>) -> Result<UniversityConfig, SnapshotError> {
    Ok(UniversityConfig {
        seed: reader.u64()?,
        start_year: reader.i32()?,
        parallelism: reader.u64()? as usize,
        init_mode: read_init_mode(reader.u8()?)?,
        master_chance: reader.f32()?,
        bachelor_weights: read_weights(reader)?,
        master_weights: read_weights(reader)?,
    })
}

fn write_population_config(writer: &mut Writer, config: &PopulationConfig) {
    writer.i32(config.start_year);
    writer.u64(config.seed);
    writer.f32(config.master_chance);
    write_weights(writer, config.bachelor_weights);
    write_weights(writer, config.master_weights);
    writer.f32(config.sensitivity_min);
    writer.f32(config.sensitivity_max);
}

fn read_population_config(reader: &mut Reader<'_>) -> Result<PopulationConfig, SnapshotError> {
    Ok(PopulationConfig {
        start_year: reader.i32()?,
        seed: reader.u64()?,
        master_chance: reader.f32()?,
        bachelor_weights: read_weights(reader)?,
        master_weights: read_weights(reader)?,
        sensitivity_min: reader.f32()?,
        sensitivity_max: reader.f32()?,
    })
}

fn write_world_config(writer: &mut Writer, config: &WorldConfig) {
    writer.u64(config.seed);
    writer.u64(config.parallelism as u64);
    writer.u8(init_mode_id(config.init_mode));
    writer.u32(config.interaction_rounds);
    writer.f32(config.relation_to_emotion_rate);
    writer.f32(config.emotion_to_relation_rate);
    writer.u64(config.influence_top_k as u64);
    writer.f32(config.influence_rate);
    writer.f32(config.influence_max_step);
    writer.f32(config.positive_relation_decay_scale);
    writer.f32(config.success_probability);
    writer.f32(config.refusal_min);
    writer.f32(config.refusal_max);
    writer.f32(config.refusal_penalty);
    writer.f32(config.refusal_relation_scale);
    writer.f32(config.refusal_context_floor);
    writer.f32(config.emotional_reaction_rate);
    writer.f32(config.base_affinity_delta);
    writer.f32(config.base_trust_delta);
    writer.f32(config.partner_positive_multiplier);
    writer.f32(config.partner_negative_multiplier);
}

fn read_world_config(reader: &mut Reader<'_>) -> Result<WorldConfig, SnapshotError> {
    Ok(WorldConfig {
        seed: reader.u64()?,
        parallelism: reader.u64()? as usize,
        init_mode: read_init_mode(reader.u8()?)?,
        interaction_rounds: reader.u32()?,
        relation_to_emotion_rate: reader.f32()?,
        emotion_to_relation_rate: reader.f32()?,
        influence_top_k: reader.u64()? as usize,
        influence_rate: reader.f32()?,
        influence_max_step: reader.f32()?,
        positive_relation_decay_scale: reader.f32()?,
        success_probability: reader.f32()?,
        refusal_min: reader.f32()?,
        refusal_max: reader.f32()?,
        refusal_penalty: reader.f32()?,
        refusal_relation_scale: reader.f32()?,
        refusal_context_floor: reader.f32()?,
        emotional_reaction_rate: reader.f32()?,
        base_affinity_delta: reader.f32()?,
        base_trust_delta: reader.f32()?,
        partner_positive_multiplier: reader.f32()?,
        partner_negative_multiplier: reader.f32()?,
    })
}

fn write_student(writer: &mut Writer, student: &Student) {
    writer.string(&student.string_id);
    writer.string(&student.name);
    writer.u8(archetype_id(student.archetype));
    writer.f32(student.sensitivity);
    writer.f32(student.sportiness);
    writer.f32(student.skip_tendency);
    for axis in EmotionAxis::ALL {
        writer.i16(student.emotions.get(axis).get());
    }
    writer.string(&student.group);
    writer.u32(student.group_id);
    writer.string(&student.faculty);
    writer.option_string(student.direction.as_deref());
    writer.i32(student.enrollment_year);
    writer.u8(student.course_year);
    writer.u8(degree_id(student.degree));
}

fn read_student(reader: &mut Reader<'_>) -> Result<Student, SnapshotError> {
    let string_id = reader.string()?;
    let name = reader.string()?;
    let archetype = read_archetype(reader.u8()?)?;
    let sensitivity = reader.f32()?;
    let sportiness = reader.f32()?;
    let skip_tendency = reader.f32()?;
    let mut emotions = EmotionVector::default();
    for axis in EmotionAxis::ALL {
        emotions.set(axis, reader.i16()?);
    }
    let group = reader.string()?;
    let group_id = reader.u32()?;
    let faculty = reader.string()?;
    let direction = reader.option_string()?;
    let enrollment_year = reader.i32()?;
    let course_year = reader.u8()?;
    let degree = read_degree(reader.u8()?)?;

    Ok(Student {
        string_id,
        name,
        archetype,
        sensitivity,
        sportiness,
        skip_tendency,
        emotions,
        group,
        group_id,
        faculty,
        direction,
        enrollment_year,
        course_year,
        degree,
    })
}

fn write_rotation(writer: &mut Writer, report: &RotationReport) {
    writer.i32(report.year);
    writer.u32(report.removed_bachelors);
    writer.u32(report.removed_masters);
    writer.u32(report.continued_bachelors);
    writer.u32(report.new_bachelors);
    writer.u32(report.new_external_masters);
    writer.u64(report.total_after as u64);
}

fn read_rotation(reader: &mut Reader<'_>) -> Result<RotationReport, SnapshotError> {
    Ok(RotationReport {
        year: reader.i32()?,
        removed_bachelors: reader.u32()?,
        removed_masters: reader.u32()?,
        continued_bachelors: reader.u32()?,
        new_bachelors: reader.u32()?,
        new_external_masters: reader.u32()?,
        total_after: reader.u64()? as usize,
    })
}

fn init_mode_id(mode: InitMode) -> u8 {
    match mode {
        InitMode::Empty => 0,
        InitMode::Random => 1,
        InitMode::Mixed => 2,
    }
}

fn read_init_mode(value: u8) -> Result<InitMode, SnapshotError> {
    match value {
        0 => Ok(InitMode::Empty),
        1 => Ok(InitMode::Random),
        2 => Ok(InitMode::Mixed),
        other => Err(SnapshotError::InvalidData(format!(
            "unknown init mode {other}"
        ))),
    }
}

fn archetype_id(kind: ArchetypeKind) -> u8 {
    ArchetypeKind::ALL
        .iter()
        .position(|candidate| *candidate == kind)
        .expect("archetype is registered") as u8
}

fn read_archetype(value: u8) -> Result<ArchetypeKind, SnapshotError> {
    ArchetypeKind::ALL
        .get(value as usize)
        .copied()
        .ok_or_else(|| SnapshotError::InvalidData(format!("unknown archetype {value}")))
}

fn degree_id(degree: Degree) -> u8 {
    match degree {
        Degree::Bachelor => 0,
        Degree::Master => 1,
    }
}

fn read_degree(value: u8) -> Result<Degree, SnapshotError> {
    match value {
        0 => Ok(Degree::Bachelor),
        1 => Ok(Degree::Master),
        other => Err(SnapshotError::InvalidData(format!(
            "unknown degree {other}"
        ))),
    }
}

#[derive(Default)]
struct Writer {
    buffer: Vec<u8>,
}

impl Writer {
    fn finish(self) -> Vec<u8> {
        self.buffer
    }

    fn bytes(&mut self, bytes: &[u8]) {
        self.buffer.extend_from_slice(bytes);
    }

    fn u8(&mut self, value: u8) {
        self.buffer.push(value);
    }

    fn u32(&mut self, value: u32) {
        self.buffer.extend_from_slice(&value.to_le_bytes());
    }

    fn u64(&mut self, value: u64) {
        self.buffer.extend_from_slice(&value.to_le_bytes());
    }

    fn i16(&mut self, value: i16) {
        self.buffer.extend_from_slice(&value.to_le_bytes());
    }

    fn i32(&mut self, value: i32) {
        self.buffer.extend_from_slice(&value.to_le_bytes());
    }

    fn f32(&mut self, value: f32) {
        self.u32(value.to_bits());
    }

    fn string(&mut self, value: &str) {
        self.u32(value.len() as u32);
        self.bytes(value.as_bytes());
    }

    fn option_string(&mut self, value: Option<&str>) {
        match value {
            Some(value) => {
                self.u8(1);
                self.string(value);
            }
            None => self.u8(0),
        }
    }
}

struct Reader<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Reader<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn is_empty(&self) -> bool {
        self.offset == self.bytes.len()
    }

    fn bytes(&mut self, length: usize) -> Result<&'a [u8], SnapshotError> {
        let end = self
            .offset
            .checked_add(length)
            .ok_or(SnapshotError::UnexpectedEof {
                offset: self.offset,
            })?;
        if end > self.bytes.len() {
            return Err(SnapshotError::UnexpectedEof {
                offset: self.offset,
            });
        }
        let slice = &self.bytes[self.offset..end];
        self.offset = end;
        Ok(slice)
    }

    fn u8(&mut self) -> Result<u8, SnapshotError> {
        Ok(self.bytes(1)?[0])
    }

    fn u32(&mut self) -> Result<u32, SnapshotError> {
        let bytes = self.bytes(4)?;
        Ok(u32::from_le_bytes(
            bytes.try_into().expect("slice has four bytes"),
        ))
    }

    fn u64(&mut self) -> Result<u64, SnapshotError> {
        let bytes = self.bytes(8)?;
        Ok(u64::from_le_bytes(
            bytes.try_into().expect("slice has eight bytes"),
        ))
    }

    fn i16(&mut self) -> Result<i16, SnapshotError> {
        let bytes = self.bytes(2)?;
        Ok(i16::from_le_bytes(
            bytes.try_into().expect("slice has two bytes"),
        ))
    }

    fn i32(&mut self) -> Result<i32, SnapshotError> {
        let bytes = self.bytes(4)?;
        Ok(i32::from_le_bytes(
            bytes.try_into().expect("slice has four bytes"),
        ))
    }

    fn f32(&mut self) -> Result<f32, SnapshotError> {
        Ok(f32::from_bits(self.u32()?))
    }

    fn string(&mut self) -> Result<String, SnapshotError> {
        let length = self.u32()? as usize;
        if length > 1 << 20 {
            return Err(SnapshotError::InvalidData(format!(
                "string length {length} is too large"
            )));
        }
        let bytes = self.bytes(length)?;
        String::from_utf8(bytes.to_vec())
            .map_err(|error| SnapshotError::InvalidData(format!("string is not UTF-8: {error}")))
    }

    fn option_string(&mut self) -> Result<Option<String>, SnapshotError> {
        match self.u8()? {
            0 => Ok(None),
            1 => Ok(Some(self.string()?)),
            other => Err(SnapshotError::InvalidData(format!(
                "option flag must be 0 or 1, got {other}"
            ))),
        }
    }

    fn count(&mut self, limit: usize) -> Result<usize, SnapshotError> {
        let count = self.u32()? as usize;
        if count > limit {
            return Err(SnapshotError::InvalidData(format!(
                "collection length {count} exceeds limit {limit}"
            )));
        }
        Ok(count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn university() -> University {
        University::new(UniversityConfig::default())
    }

    #[test]
    fn round_trip_preserves_the_persistent_state() {
        let mut original = university();
        for _ in 0..5 {
            original.step_day();
        }
        let bytes = original.to_snapshot();
        let restored = University::from_snapshot(&bytes).expect("snapshot");

        assert_eq!(restored.state_hash(), original.state_hash());
        assert_eq!(restored.rng.state(), original.rng.state());
        assert_eq!(
            restored.population.rng_state(),
            original.population.rng_state()
        );
        assert_eq!(restored.days_completed(), original.days_completed());
        assert_eq!(restored.len(), original.len());
        assert_eq!(restored.population.total(), original.population.total());
        assert_eq!(restored.schedules.len(), original.schedules.len());
        assert_eq!(restored.rotations.len(), original.rotations.len());
        assert_eq!(restored.world.relations, original.world.relations);
    }

    #[test]
    fn resumed_run_matches_a_continuous_run() {
        let mut continuous = university();
        for _ in 0..4 {
            continuous.step_day();
        }
        let snapshot = continuous.to_snapshot();
        let mut resumed = University::from_snapshot(&snapshot).expect("snapshot");

        for _ in 0..6 {
            continuous.step_day();
            resumed.step_day();
        }
        assert_eq!(resumed.state_hash(), continuous.state_hash());
        assert_eq!(resumed.rng.state(), continuous.rng.state());
        assert_eq!(resumed.world.relations, continuous.world.relations);
    }

    #[test]
    #[ignore = "expensive: runs an academic year; run in release with --ignored"]
    fn snapshot_can_resume_across_an_academic_rotation() {
        let mut continuous = university();
        for _ in 0..303 {
            continuous.step_day();
        }
        assert!(continuous.rotations.is_empty());

        let snapshot = continuous.to_snapshot();
        let mut resumed = University::from_snapshot(&snapshot).expect("load");
        for _ in 0..8 {
            continuous.step_day();
            resumed.step_day();
        }

        assert_eq!(resumed.state_hash(), continuous.state_hash());
        assert_eq!(resumed.rotations.len(), continuous.rotations.len());
        assert_eq!(resumed.rotations.len(), 1);
    }

    #[test]
    fn corrupt_snapshots_are_rejected() {
        assert!(matches!(
            University::from_snapshot(b"not a snapshot"),
            Err(SnapshotError::InvalidMagic)
        ));

        let mut bytes = university().to_snapshot();
        bytes[8] = 99;
        assert!(matches!(
            University::from_snapshot(&bytes),
            Err(SnapshotError::UnsupportedVersion(99))
        ));

        let bytes = university().to_snapshot();
        assert!(matches!(
            University::from_snapshot(&bytes[..bytes.len() - 1]),
            Err(SnapshotError::UnexpectedEof { .. })
        ));
    }
}
