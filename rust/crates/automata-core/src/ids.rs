/// Stable, dense identifier of an agent inside one simulation run.
///
/// The index is assigned once in `World::from_specs` and never reused for a
/// different person inside the same run.  Academic rotation in v3 will keep
/// the string identifier stable and may assign a new dense index only when the
/// engine is rebuilt.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct AgentId(pub u32);

impl AgentId {
    pub const fn new(value: u32) -> Self {
        Self(value)
    }

    pub const fn index(self) -> usize {
        self.0 as usize
    }
}
