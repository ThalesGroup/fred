# Evaluate the review procedure

Use this when changing the procedure substantially or checking a recurring
miss, not as a prerequisite for every PR. It measures detection, not compliance
with headings or a count of findings.

1. Select a small set of real pre-fix changes and their corrected counterparts.
   Keep expected findings, their fixes and the case labels out of reviewer input.
   Prefer a held-out defect family when evaluating generalization; examples used
   to write the skill only demonstrate that its instructions can be followed.
2. Prepare read-only snapshots in a temporary directory or isolated checkout.
   Supply the same requirements and sufficient consumer context for both versions.
   Do not execute untrusted historical code without the applicable review policy.
3. Give a fresh reviewer only the skill, a realistic review request and the raw
   snapshots. Ask for concrete trigger/impact evidence and declared exclusions.
   Do not provide the author's rationale, prior findings or expected answer.
4. Compare findings against the known defects and fixed controls: record detected,
   missed and unsupported findings, plus cost/time when relevant. Investigate
   unexpected findings rather than automatically labeling them false positives.
5. Record the result in the current task or PR. Adjust instructions only for an
   observed gap. Keep product regressions in the existing test suites; do not
   commit copied production snapshots or introduce a second test runner by default.

A successful replay is limited evidence for those cases, not proof that review
is complete. New defect families need independent examples.


For claims that an instruction change improves review quality, compare the old
and revised procedures on equivalent held-out cases, with separate fresh
contexts and the same scope/time allowance. Keep known examples used to write
the procedure out of this comparison. Include fixed controls to reveal invented
findings, and a composition or lifecycle case different from the motivating bug.
Record supported detections, misses and unsupported findings against the same
case set. More findings alone is not improvement. If fresh reviewers are
unavailable, report the evaluation as pending; a self-replay cannot substitute
for it. Do not claim knowledge of a remote reviewer's model, prompt or method
without evidence.
