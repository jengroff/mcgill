use pyo3::prelude::*;

/// Jaro-Winkler similarity between two strings.
#[pyfunction]
fn jaro_winkler(s1: &str, s2: &str, prefix_weight: f64) -> f64 {
    if s1 == s2 {
        return 1.0;
    }
    if s1.is_empty() || s2.is_empty() {
        return 0.0;
    }

    let s1_bytes = s1.as_bytes();
    let s2_bytes = s2.as_bytes();
    let len1 = s1_bytes.len();
    let len2 = s2_bytes.len();

    let max_dist = (len1.max(len2) / 2).saturating_sub(1);

    let mut s1_matched = vec![false; len1];
    let mut s2_matched = vec![false; len2];
    let mut matches = 0usize;
    let mut transpositions = 0usize;

    for i in 0..len1 {
        let start = i.saturating_sub(max_dist);
        let end = (i + max_dist + 1).min(len2);
        for j in start..end {
            if s2_matched[j] || s1_bytes[i] != s2_bytes[j] {
                continue;
            }
            s1_matched[i] = true;
            s2_matched[j] = true;
            matches += 1;
            break;
        }
    }

    if matches == 0 {
        return 0.0;
    }

    let mut k = 0usize;
    for i in 0..len1 {
        if !s1_matched[i] {
            continue;
        }
        while !s2_matched[k] {
            k += 1;
        }
        if s1_bytes[i] != s2_bytes[k] {
            transpositions += 1;
        }
        k += 1;
    }

    let m = matches as f64;
    let jaro = (m / len1 as f64 + m / len2 as f64 + (m - transpositions as f64 / 2.0) / m) / 3.0;

    let prefix_len = s1_bytes
        .iter()
        .zip(s2_bytes.iter())
        .take(4)
        .take_while(|(a, b)| a == b)
        .count();

    jaro + prefix_len as f64 * prefix_weight * (1.0 - jaro)
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(jaro_winkler, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_jaro_winkler_identical() {
        let sim = jaro_winkler("hello", "hello", 0.1);
        assert!((sim - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_jaro_winkler_similar() {
        let sim = jaro_winkler("martha", "marhta", 0.1);
        assert!(sim > 0.9);
    }

    #[test]
    fn test_jaro_winkler_empty() {
        assert!((jaro_winkler("", "hello", 0.1)).abs() < 1e-6);
        assert!((jaro_winkler("hello", "", 0.1)).abs() < 1e-6);
    }

    #[test]
    fn test_jaro_winkler_dissimilar() {
        let sim = jaro_winkler("abcdef", "zyxwvu", 0.1);
        assert!(sim < 0.5);
    }
}
