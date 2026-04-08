use pyo3::prelude::*;

#[inline(always)]
fn blsi(x: u64) -> u64 {
    x & x.wrapping_neg()
}

#[inline(always)]
fn blsr(x: u64) -> u64 {
    x & x.wrapping_sub(1)
}

#[inline(always)]
fn lsb_mask(n: usize) -> u64 {
    if n >= 64 {
        !0u64
    } else {
        (1u64 << n) - 1
    }
}

/// Jaro similarity via bitparallel matching (single u64 word).
/// `pattern` must be the shorter string; both must be <= 64 bytes.
fn jaro_bitparallel(pattern: &[u8], text: &[u8]) -> f64 {
    let len_p = pattern.len();
    let len_t = text.len();
    let bound = (len_p.max(len_t) / 2).saturating_sub(1);

    // Build character bitmask table: pm[c] has bit i set iff pattern[i] == c
    let mut pm = [0u64; 256];
    for (i, &b) in pattern.iter().enumerate() {
        pm[b as usize] |= 1u64 << i;
    }

    let mut p_flag: u64 = 0;
    let mut t_flag: u64 = 0;
    let mut bound_mask = lsb_mask(bound + 1);

    // Phase 1: window still growing (left edge pinned at 0)
    let phase1_end = bound.min(len_t);
    for j in 0..phase1_end {
        let pm_j = pm[text[j] as usize] & bound_mask & !p_flag;
        p_flag |= blsi(pm_j);
        t_flag |= u64::from(pm_j != 0) << j;
        bound_mask = (bound_mask << 1) | 1;
    }

    // Phase 2: window sliding (both edges advance)
    for j in phase1_end..len_t {
        let pm_j = pm[text[j] as usize] & bound_mask & !p_flag;
        p_flag |= blsi(pm_j);
        t_flag |= u64::from(pm_j != 0) << j;
        bound_mask <<= 1;
    }

    let matches = p_flag.count_ones();
    if matches == 0 {
        return 0.0;
    }

    // Count transpositions by walking matched positions in order
    let mut transpositions = 0u32;
    let mut pf = p_flag;
    let mut tf = t_flag;
    while tf != 0 {
        let pat_bit = blsi(pf);
        let t_pos = tf.trailing_zeros() as usize;
        if pm[text[t_pos] as usize] & pat_bit == 0 {
            transpositions += 1;
        }
        tf = blsr(tf);
        pf ^= pat_bit;
    }

    let m = matches as f64;
    let t = (transpositions / 2) as f64;
    (m / len_p as f64 + m / len_t as f64 + (m - t) / m) / 3.0
}

/// Jaro similarity via the naive O(NM) algorithm (fallback for strings > 64 bytes).
fn jaro_naive(s1: &[u8], s2: &[u8]) -> f64 {
    let len1 = s1.len();
    let len2 = s2.len();
    let max_dist = (len1.max(len2) / 2).saturating_sub(1);

    let mut s1_matched = vec![false; len1];
    let mut s2_matched = vec![false; len2];
    let mut matches = 0usize;

    for i in 0..len1 {
        let start = i.saturating_sub(max_dist);
        let end = (i + max_dist + 1).min(len2);
        for j in start..end {
            if s2_matched[j] || s1[i] != s2[j] {
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

    let mut transpositions = 0usize;
    let mut k = 0usize;
    for i in 0..len1 {
        if !s1_matched[i] {
            continue;
        }
        while !s2_matched[k] {
            k += 1;
        }
        if s1[i] != s2[k] {
            transpositions += 1;
        }
        k += 1;
    }

    let m = matches as f64;
    let t = (transpositions / 2) as f64;
    (m / len1 as f64 + m / len2 as f64 + (m - t) / m) / 3.0
}

/// Jaro-Winkler similarity between two strings.
#[pyfunction]
fn jaro_winkler(s1: &str, s2: &str, prefix_weight: f64) -> f64 {
    if s1 == s2 {
        return 1.0;
    }
    if s1.is_empty() || s2.is_empty() {
        return 0.0;
    }

    let (short, long) = if s1.len() <= s2.len() {
        (s1.as_bytes(), s2.as_bytes())
    } else {
        (s2.as_bytes(), s1.as_bytes())
    };

    let jaro = if long.len() <= 64 {
        jaro_bitparallel(short, long)
    } else {
        jaro_naive(short, long)
    };

    if jaro == 0.0 {
        return 0.0;
    }

    let prefix_len = s1
        .as_bytes()
        .iter()
        .zip(s2.as_bytes().iter())
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

    #[test]
    fn test_bitparallel_matches_naive() {
        let pairs = [
            ("martha", "marhta"),
            ("hello", "hallo"),
            ("abc", "xyz"),
            ("a", "a"),
            ("ab", "ba"),
            ("kitten", "sitting"),
            ("Saturday", "Sunday"),
            ("introduction to organic chemistry", "intro organic chem"),
            ("Neuroanatomy and Neurophysiology", "Neuroanatomy"),
            ("International Development Studies", "Intl Development"),
        ];
        for (s1, s2) in pairs {
            let (short, long) = if s1.len() <= s2.len() {
                (s1.as_bytes(), s2.as_bytes())
            } else {
                (s2.as_bytes(), s1.as_bytes())
            };
            let bp = jaro_bitparallel(short, long);
            let naive = jaro_naive(short, long);
            assert!(
                (bp - naive).abs() < 1e-10,
                "({s1}, {s2}): bitparallel={bp}, naive={naive}"
            );
        }
    }
}
