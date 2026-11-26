//! Deterministic data-parallel helpers.
//!
//! The model has two useful shapes of parallelism:
//!
//! * one mutable agent at a time (emotion decay, influence);
//! * one mutable agent plus its own outgoing relation row (relation decay,
//!   emotion -> relation reactions).
//!
//! Both split a contiguous slice into chunks.  Every chunk writes only its own
//! agents/rows, so the result is independent of the number of threads.  There
//! is no shared RNG and no `reduce` over floating-point values in these phases.

use crate::agent::Agent;
use crate::relation::Relation;

fn chunk_size(len: usize, parallelism: usize) -> usize {
    if len == 0 {
        return 0;
    }
    let effective = parallelism.max(1).min(len);
    len.div_ceil(effective)
}

/// Runs `f(global_index, agent)` over disjoint agent chunks.
pub(crate) fn for_each_agent_indexed_mut<F>(agents: &mut [Agent], parallelism: usize, f: F)
where
    F: Fn(usize, &mut Agent) + Sync,
{
    if parallelism <= 1 || agents.len() < 2 {
        for (index, agent) in agents.iter_mut().enumerate() {
            f(index, agent);
        }
        return;
    }

    let chunk = chunk_size(agents.len(), parallelism);
    std::thread::scope(|scope| {
        let mut offset = 0;
        for slice in agents.chunks_mut(chunk) {
            let start = offset;
            let count = slice.len();
            let f = &f;
            scope.spawn(move || {
                for (local, agent) in slice.iter_mut().enumerate() {
                    f(start + local, agent);
                }
            });
            offset += count;
        }
    });
}

/// Runs `f(global_index, agent, outgoing_row)` over disjoint agent/row chunks.
pub(crate) fn for_each_agent_row_mut<F>(
    agents: &mut [Agent],
    relations: &mut [Relation],
    row_len: usize,
    parallelism: usize,
    f: F,
) where
    F: Fn(usize, &mut Agent, &mut [Relation]) + Sync,
{
    assert!(row_len > 0, "relation row length must be positive");
    assert_eq!(
        relations.len(),
        agents.len() * row_len,
        "relation matrix must be rectangular"
    );

    if parallelism <= 1 || agents.len() < 2 {
        for (index, agent) in agents.iter_mut().enumerate() {
            let start = index * row_len;
            f(index, agent, &mut relations[start..start + row_len]);
        }
        return;
    }

    let chunk = chunk_size(agents.len(), parallelism);
    std::thread::scope(|scope| {
        let mut offset = 0;
        let mut agent_chunks = agents.chunks_mut(chunk);
        let mut relation_chunks = relations.chunks_mut(chunk * row_len);

        while let (Some(agent_slice), Some(relation_slice)) =
            (agent_chunks.next(), relation_chunks.next())
        {
            let start = offset;
            let count = agent_slice.len();
            let f = &f;
            scope.spawn(move || {
                for (local, agent) in agent_slice.iter_mut().enumerate() {
                    let rel_start = local * row_len;
                    f(
                        start + local,
                        agent,
                        &mut relation_slice[rel_start..rel_start + row_len],
                    );
                }
            });
            offset += count;
        }
    });
}
