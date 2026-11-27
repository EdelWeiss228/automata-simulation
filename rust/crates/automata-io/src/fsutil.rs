//! Small filesystem helpers with atomic replacement semantics.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

pub fn write_atomic(path: &Path, bytes: &[u8]) -> io::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let temporary = temporary_path(path);
    {
        use std::io::Write;
        let mut file = fs::File::create(&temporary)?;
        file.write_all(bytes)?;
        file.sync_all()?;
    }
    fs::rename(&temporary, path)?;
    Ok(())
}

pub fn truncate_to(path: &Path, length: u64) -> io::Result<()> {
    if !path.exists() {
        if length == 0 {
            return Ok(());
        }
        return Err(io::Error::new(
            io::ErrorKind::NotFound,
            format!(
                "{} is missing but the manifest expects {length} bytes",
                path.display()
            ),
        ));
    }
    let current = fs::metadata(path)?.len();
    if current < length {
        return Err(io::Error::new(
            io::ErrorKind::InvalidData,
            format!(
                "{} has {current} bytes but the manifest expects at least {length}",
                path.display()
            ),
        ));
    }
    if current == length {
        return Ok(());
    }
    let file = fs::OpenOptions::new().write(true).open(path)?;
    file.set_len(length)?;
    file.sync_all()?;
    Ok(())
}

fn temporary_path(path: &Path) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(format!(".tmp.{}", std::process::id()));
    PathBuf::from(name)
}
