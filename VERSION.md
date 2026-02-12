# Version History

## V5.2 (Latest)
- **High-Performance Logging**: Moved CSV writing to C++ module (`logger.cpp`).
- **Full Daily Cycle**: Entire calculation loop migrated to C++ with OpenMP support.
- **Dynamic Sync**: Optimized data transfer between C++ and Python (skips relations sync in silent mode).
- **Architecture**: Separated core engine logic, logging, and Python bindings into clean modules.

## V5.1
- Initial C++ core integration for performance.
- Archetype synchronization between Python and C++.

## V5.0
- Base project structure with Python-based agents and University model.
