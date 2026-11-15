// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Bounded exact populations; ratios use decimal long division, never lossy floats.
pub(crate) fn ratio(n: u128, d: u128) -> Option<String> {
    if d == 0 {
        return None;
    }
    let mut out = (n / d).to_string();
    let mut remainder = n % d;
    if remainder != 0 {
        out.push('.');
        for _ in 0..6 {
            remainder *= 10;
            out.push(char::from(b'0' + (remainder / d) as u8));
            remainder %= d;
            if remainder == 0 {
                break;
            }
        }
    }
    Some(out)
}
pub(crate) fn median(mut counts: Vec<u128>) -> Option<String> {
    counts.sort_unstable();
    let n = counts.len();
    if n == 0 {
        None
    } else if n % 2 == 1 {
        Some(counts[n / 2].to_string())
    } else {
        ratio(counts[n / 2 - 1] + counts[n / 2], 2)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn empty_denominators_and_exact_large_medians() {
        assert_eq!(ratio(1, 0), None);
        assert_eq!(ratio(1, 3).as_deref(), Some("0.333333"));
        assert_eq!(
            median(vec![9007199254740993, 9007199254740994]).as_deref(),
            Some("9007199254740993.5")
        );
    }
}
