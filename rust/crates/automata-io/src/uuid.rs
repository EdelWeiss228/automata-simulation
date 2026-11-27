//! Dependency-free UUID v5 support for stable ClickHouse run identifiers.

use std::fmt;
use std::str::FromStr;

use crate::sha1::sha1;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Uuid([u8; 16]);

impl Uuid {
    /// RFC 4122 URL namespace.  Used as the namespace for v3 run IDs.
    pub const NAMESPACE_URL: Self = Self([
        0x6b, 0xa7, 0xb8, 0x11, 0x9d, 0xad, 0x11, 0xd1, 0x80, 0xb4, 0x00, 0xc0, 0x4f, 0xd4, 0x30,
        0xc8,
    ]);

    pub const fn from_bytes(bytes: [u8; 16]) -> Self {
        Self(bytes)
    }

    pub fn v5(namespace: Self, name: &[u8]) -> Self {
        let mut input = Vec::with_capacity(16 + name.len());
        input.extend_from_slice(&namespace.0);
        input.extend_from_slice(name);
        let digest = sha1(&input);

        let mut bytes = [0u8; 16];
        bytes.copy_from_slice(&digest[..16]);
        bytes[6] = (bytes[6] & 0x0F) | 0x50;
        bytes[8] = (bytes[8] & 0x3F) | 0x80;
        Self(bytes)
    }

    pub const fn as_bytes(&self) -> &[u8; 16] {
        &self.0
    }

    pub fn version(self) -> u8 {
        self.0[6] >> 4
    }

    pub fn to_hyphenated(self) -> String {
        let mut text = String::with_capacity(36);
        for (index, byte) in self.0.iter().enumerate() {
            if matches!(index, 4 | 6 | 8 | 10) {
                text.push('-');
            }
            use std::fmt::Write;
            let _ = write!(text, "{byte:02x}");
        }
        text
    }

    pub fn parse(value: &str) -> Result<Self, UuidError> {
        value.parse()
    }
}

impl fmt::Display for Uuid {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(&self.to_hyphenated())
    }
}

impl FromStr for Uuid {
    type Err = UuidError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        let compact: String = value
            .chars()
            .filter(|character| *character != '-')
            .collect();
        if compact.len() != 32 {
            return Err(UuidError::InvalidLength);
        }

        let mut bytes = [0u8; 16];
        for (index, byte) in bytes.iter_mut().enumerate() {
            let start = index * 2;
            *byte = u8::from_str_radix(&compact[start..start + 2], 16)
                .map_err(|_| UuidError::InvalidHex)?;
        }
        Ok(Self(bytes))
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum UuidError {
    InvalidLength,
    InvalidHex,
}

impl fmt::Display for UuidError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidLength => formatter.write_str("UUID must contain 32 hexadecimal digits"),
            Self::InvalidHex => formatter.write_str("UUID contains a non-hexadecimal digit"),
        }
    }
}

impl std::error::Error for UuidError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn formats_and_parses_round_trip() {
        let text = "2ed6657d-e927-568b-95e1-2665a8aea6a2";
        let uuid = Uuid::parse(text).expect("uuid");
        assert_eq!(uuid.to_hyphenated(), text);
        assert_eq!(uuid.version(), 5);
        assert_eq!(uuid.to_string(), text);
    }

    #[test]
    fn rejects_bad_input() {
        assert_eq!(Uuid::parse("nope"), Err(UuidError::InvalidLength));
        assert_eq!(
            Uuid::parse("zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"),
            Err(UuidError::InvalidHex)
        );
    }

    #[test]
    fn matches_rfc_4122_v5() {
        // Python: uuid.uuid5(uuid.NAMESPACE_URL, "https://example.com")
        let uuid = Uuid::v5(Uuid::NAMESPACE_URL, b"https://example.com");
        assert_eq!(uuid.to_hyphenated(), "4fd35a71-71ef-5a55-a9d9-aa75c889a6d0");
    }
}
