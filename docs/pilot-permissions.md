# Effective permissions for the manufacturing pilot

Account administration and operating permissions are separate. All private routes first authenticate current organization membership, then check assignment scope. Browser visibility is not an authorization boundary.

| Action | Owner | Supervisor | Worker | Authorized reviewer |
|---|---|---|---|---|
| Read operational records | Organization-wide; select a dated shift or legacy archive | Assigned shifts/items and linked incoming evidence | Assigned shifts/items and linked evidence | Assigned shifts/items |
| People, elevated roles, settings, export | Yes | No | No | No |
| Add ordinary workers as delegated administrator | Yes | Only with separate admin access | No | Only with separate admin access |
| Create/coordinate work | With supervisor permission; owner who explicitly becomes reviewer retains coordination | Assigned team/scope | No | No, unless owner with explicit reviewer permission |
| Record updates | Authorized work items | Authorized work items | Authorized work items and recording-time assignment | Authorized work items |
| Review ordinary interpretations | Supervisor/reviewer permission | Within scope | No | Within scope |
| Clear protected holds | Explicit reviewer permission only | No | No | Within scope, with source and reason |
| Assign tasks | Coordination permission | Within scope, active named assignees | No | Owner-reviewer only |
| Report task done | If assigned | If assigned | If assigned | If assigned |
| Verify completion | Review permission | Within scope | No | Within scope |
| Recover unfinished submissions | Review permission; audited reason | Within scope; audited reason | Own empty draft only | Within scope; audited reason |
| Change whole-shift assignments / close shift | Coordination permission | Designated supervisor with full shift scope | No | Owner-reviewer only |
| Acknowledge handover | Only when assigned recipient | Only when assigned recipient | Own assigned handover | Only when assigned recipient |

A receipt confirms that the displayed version was received; it does not certify objective correctness or remove outstanding holds. Versions are scoped to a dated shift, not each individual item; another material change inside that same shift can require a new acknowledgement. Stored snapshots never change. Current permission checks can deny access to an old snapshot containing subsequently revoked work.

Workers do not receive coworker email addresses, organization exports, team administration or benchmark pages. Scoped directories return only IDs, names and roles. Employee credentials are organization-specific; password reset or removal from one organization does not reset another account. Worker removal and role changes are recorded without deleting original reports.

Legacy data without genuine shift assignments remains an owner-visible archive. The application does not fabricate old team/shift assignments from names or upload timestamps. The fictional `/demo` has its own identity mechanism and data store; those identities cannot enter organization routes.
