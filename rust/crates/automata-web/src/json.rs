//! Minimal JSON helpers for the std-only web layer.

/// Escapes a string for embedding inside a JSON string literal.
pub fn escape(input: &str) -> String {
    let mut output = String::with_capacity(input.len());
    for character in input.chars() {
        match character {
            '"' => output.push_str("\\\""),
            '\\' => output.push_str("\\\\"),
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character < ' ' => {
                output.push_str(&format!("\\u{:04x}", character as u32));
            }
            character => output.push(character),
        }
    }
    output
}

/// Renders a JSON string literal.
pub fn string(value: &str) -> String {
    format!("\"{}\"", escape(value))
}

/// Renders a finite number, or `null` for NaN/infinity.
pub fn number(value: f64) -> String {
    if value.is_finite() {
        format!("{value:.6}")
    } else {
        "null".to_string()
    }
}

/// Renders a `key: value` pair with an escaped key.
pub fn field(key: &str, value: &str) -> String {
    format!("{}:{}", string(key), value)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escapes_quotes_and_control_characters() {
        assert_eq!(escape("a\"b\\c\n\t"), "a\\\"b\\\\c\\n\\t");
        assert_eq!(escape("\u{1}"), "\\u0001");
        assert_eq!(string("привет"), "\"привет\"");
    }

    #[test]
    fn non_finite_numbers_become_null() {
        assert_eq!(number(f64::NAN), "null");
        assert_eq!(number(f64::INFINITY), "null");
        assert_eq!(number(1.5), "1.500000");
    }
}
