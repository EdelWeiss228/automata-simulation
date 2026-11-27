//! Small streaming CSV writer used by the batch runner.
//!
//! The writer tracks the exact byte length of the file.  The manifest stores
//! that length after every completed day, so a resumed run can truncate a
//! partially written day before replaying it.

use std::fmt::Display;
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufWriter, Write};
use std::path::{Path, PathBuf};

#[derive(Clone, Debug)]
pub struct CsvRow {
    buffer: String,
}

impl CsvRow {
    pub fn new() -> Self {
        Self {
            buffer: String::with_capacity(128),
        }
    }

    pub fn clear(&mut self) {
        self.buffer.clear();
    }

    pub fn field(&mut self, value: &str) -> &mut Self {
        push_escaped(&mut self.buffer, value);
        self.buffer.push(',');
        self
    }

    pub fn display(&mut self, value: impl Display) -> &mut Self {
        use std::fmt::Write;
        let _ = write!(self.buffer, "{value}");
        self.buffer.push(',');
        self
    }

    pub fn finish(&mut self) -> &str {
        if self.buffer.ends_with(',') {
            self.buffer.pop();
        }
        self.buffer.push('\n');
        &self.buffer
    }
}

impl Default for CsvRow {
    fn default() -> Self {
        Self::new()
    }
}

pub struct CsvFile {
    path: PathBuf,
    writer: BufWriter<File>,
    bytes: u64,
}

impl CsvFile {
    pub fn open(path: impl Into<PathBuf>, header: Option<&[&str]>) -> io::Result<Self> {
        let path = path.into();
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        let existed = path.exists();
        let bytes = if existed {
            fs::metadata(&path)?.len()
        } else {
            0
        };
        let file = OpenOptions::new().create(true).append(true).open(&path)?;
        let mut csv = Self {
            path,
            writer: BufWriter::with_capacity(256 * 1024, file),
            bytes,
        };
        if bytes == 0
            && let Some(header) = header
        {
            let mut row = CsvRow::new();
            for field in header {
                row.field(field);
            }
            csv.write_row(&mut row)?;
        }
        Ok(csv)
    }

    pub fn path(&self) -> &Path {
        &self.path
    }

    pub fn len(&self) -> u64 {
        self.bytes
    }

    pub fn is_empty(&self) -> bool {
        self.bytes == 0
    }

    pub fn write_row(&mut self, row: &mut CsvRow) -> io::Result<()> {
        let line = row.finish().as_bytes().to_vec();
        self.writer.write_all(&line)?;
        self.bytes += line.len() as u64;
        Ok(())
    }

    /// Appends an already formatted block of CSV rows.
    pub fn write_raw(&mut self, text: &str) -> io::Result<()> {
        if text.is_empty() {
            return Ok(());
        }
        self.writer.write_all(text.as_bytes())?;
        self.bytes += text.len() as u64;
        Ok(())
    }

    pub fn flush(&mut self) -> io::Result<()> {
        self.writer.flush()
    }

    /// Drops a partially written suffix, then reopens the file for appending.
    pub fn truncate_to(&mut self, length: u64) -> io::Result<()> {
        self.writer.flush()?;
        let file = OpenOptions::new().write(true).open(&self.path)?;
        file.set_len(length)?;
        file.sync_all()?;
        drop(file);
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)?;
        self.writer = BufWriter::with_capacity(256 * 1024, file);
        self.bytes = length;
        Ok(())
    }
}

fn push_escaped(output: &mut String, value: &str) {
    if !value.contains([',', '"', '\n', '\r']) {
        output.push_str(value);
        return;
    }
    output.push('"');
    for character in value.chars() {
        if character == '"' {
            output.push('"');
        }
        output.push(character);
    }
    output.push('"');
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temporary_path(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "automata-csv-{}-{}-{name}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn escapes_commas_quotes_and_newlines() {
        let mut row = CsvRow::new();
        row.field("plain")
            .field("a,b")
            .field("say \"hi\"")
            .field("line\nbreak");
        assert_eq!(
            row.finish(),
            "plain,\"a,b\",\"say \"\"hi\"\"\",\"line\nbreak\"\n"
        );
    }

    #[test]
    fn writes_a_header_only_once() {
        let path = temporary_path("header.csv");
        {
            let mut file = CsvFile::open(&path, Some(&["a", "b"])).unwrap();
            let mut row = CsvRow::new();
            row.field("1").field("2");
            file.write_row(&mut row).unwrap();
            file.flush().unwrap();
        }
        {
            let mut file = CsvFile::open(&path, Some(&["a", "b"])).unwrap();
            let mut row = CsvRow::new();
            row.field("3").field("4");
            file.write_row(&mut row).unwrap();
            file.flush().unwrap();
        }
        let text = fs::read_to_string(&path).unwrap();
        assert_eq!(text, "a,b\n1,2\n3,4\n");
        fs::remove_file(path).unwrap();
    }

    #[test]
    fn truncates_a_partial_day() {
        let path = temporary_path("truncate.csv");
        let mut file = CsvFile::open(&path, Some(&["a", "b"])).unwrap();
        let mut row = CsvRow::new();
        row.field("1").field("2");
        file.write_row(&mut row).unwrap();
        let complete = file.len();

        row = CsvRow::new();
        row.field("partial");
        file.write_row(&mut row).unwrap();
        file.flush().unwrap();

        file.truncate_to(complete).unwrap();
        file.flush().unwrap();
        assert_eq!(fs::read_to_string(&path).unwrap(), "a,b\n1,2\n");
        assert_eq!(file.len(), complete);
        fs::remove_file(path).unwrap();
    }
}
