# Design

Keep `activity_review.QUALIFIED_EXECUTION` as the single shipped permit:
`(5, 28.0)`. Reuse the existing sequential loop, `recovery_read`, exact
readback and v3 journal. The delay remains between confirmed corrections before
fresh evidence is read. Do not add a setting or destination integration.

The value is evidence-based. RC2 observed a maximum request-response to
portfolio-cache completion chain of 18.19 seconds. A 1.5x margin gives 27.285
seconds; ship 28.0 seconds. A future longer chain requires a new release. Exact
readback and the first-uncertainty stop remain the data safety fence.

Update the default-permit test and the operator/specification surfaces. The
existing mocked delay tests remain synthetic and do not qualify Ghostfolio.

Rollback restores the prior qualified image and permit. It does not reverse any
financial write. Preserve review files, journals and evidence.
