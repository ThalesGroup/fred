## Purpose

Lets each person set and remove their own profile picture, and shows it wherever Fred identifies that person with an avatar, falling back to initials when there is none.

## ADDED Requirements

### Requirement: A person sets their own profile picture

The control plane SHALL let an authenticated person upload a profile picture for themselves only. A successful upload SHALL replace any previous picture of that person. No endpoint SHALL let one person set another person's picture.

#### Scenario: First upload

- **WHEN** Alice, who has no picture, uploads a valid 200 KB PNG to her own profile picture endpoint
- **THEN** the request succeeds and Alice's user summary now carries a picture URL

#### Scenario: Replacing a picture

- **WHEN** Alice, who already has a picture, uploads a new valid picture
- **THEN** the request succeeds, her summary carries a URL for the new picture, and the URL differs from the previous one

#### Scenario: No way to target another person

- **WHEN** Bob calls the profile picture endpoints
- **THEN** only Bob's own picture can be read back as changed; no request parameter designates another person

### Requirement: Uploads are validated like team avatars

The control plane SHALL reject a profile picture upload that is empty, larger than 5 MB, declared with a content type other than JPEG, PNG or WebP, or whose actual content does not match an allowed image format or does not match the declared type. A rejected upload SHALL leave the person's existing picture unchanged. Team avatar uploads SHALL apply the same rules with the same limits.

#### Scenario: File too large

- **WHEN** Alice uploads a 6 MB JPEG
- **THEN** the request is rejected with a client error and her existing picture, if any, is unchanged

#### Scenario: Declared type does not match content

- **WHEN** Alice uploads a file declared as `image/png` whose bytes are a JPEG
- **THEN** the request is rejected with a client error

#### Scenario: Unsupported format

- **WHEN** Alice uploads a GIF
- **THEN** the request is rejected with a client error

### Requirement: A person deletes their own profile picture

The control plane SHALL let an authenticated person delete their own profile picture. Deletion SHALL be idempotent: deleting when no picture exists SHALL succeed and change nothing. After deletion the person's user summary SHALL carry no picture URL.

#### Scenario: Deleting an existing picture

- **WHEN** Alice, who has a picture, deletes it
- **THEN** the request succeeds and her user summary carries no picture URL

#### Scenario: Deleting when there is none

- **WHEN** Alice, who has no picture, deletes her picture
- **THEN** the request succeeds with the same response as a real deletion

### Requirement: Replaced and deleted pictures leave object storage

When a profile picture is replaced, deleted, or its owner's account is deleted through the identity provider, the control plane SHALL remove the previous picture's object from object storage, on every supported storage backend. A failure to remove the old object SHALL NOT fail the user's request once the new state is recorded; it SHALL be logged without the picture content or any presigned URL.

#### Scenario: Replace removes the old object

- **WHEN** Alice replaces her picture
- **THEN** the object holding her previous picture no longer exists in object storage

#### Scenario: Delete removes the object

- **WHEN** Alice deletes her picture
- **THEN** the object holding it no longer exists in object storage

#### Scenario: Account deletion removes the object

- **WHEN** an administrator deletes Alice's account through the identity provider and Alice had a picture
- **THEN** the object holding it no longer exists in object storage and no picture key remains recorded for her

#### Scenario: Local directory deletion keeps the picture

- **WHEN** an administrator deletes Alice's account in the local user directory, which only suspends it
- **THEN** her picture and its key are kept, like her other data

#### Scenario: Old object removal fails

- **WHEN** Alice replaces her picture and object storage refuses to delete the previous object
- **THEN** the request still succeeds, her summary shows the new picture, and a warning is logged without image data or URLs

### Requirement: User summaries carry the picture URL where it renders

The user summaries that render a person's avatar — the bootstrap's current user and team administrator summaries — SHALL include an optional temporary picture URL when that person has a picture, and SHALL omit it otherwise. Summaries that render no picture — team member lists, platform-role holders and the batch lookup by ids — SHALL NOT carry it, so they cost no picture lookup. Resolving pictures for a batch SHALL read the stored picture keys for all requested people in one storage query, SHALL produce URLs only for people who have a picture, and SHALL bound how many URLs are produced at once. A URL that cannot be produced SHALL be omitted rather than failing the request. A newly uploaded or deleted picture SHALL be reflected in the next summary returned, without waiting for any display-name cache to expire.

#### Scenario: Team administrators with mixed people

- **WHEN** a team lists Alice (with picture) and Bob (without) as administrators
- **THEN** Alice's administrator summary has a picture URL and Bob's has none

#### Scenario: Text-only summaries carry no URL

- **WHEN** the frontend resolves Alice's id through the batch lookup, a team member list or the platform-role list
- **THEN** her summary has no picture URL and no picture key is read

#### Scenario: Picture change is visible immediately

- **WHEN** Alice uploads a picture and the frontend then reloads the bootstrap or a team where she is an administrator
- **THEN** her summary carries the new picture URL even though her display name was cached moments before

#### Scenario: URL generation fails

- **WHEN** object storage cannot produce a URL for Alice's picture
- **THEN** her summary is returned without a picture URL and the request succeeds

### Requirement: The picture replaces initials where a person's avatar is shown

The frontend SHALL show a person's picture instead of their initials in every place that renders that person's avatar: the navigation-rail profile, the user settings page, the personal-space header, the personal entry of the home team list, and team administrator avatars on team cards and the admin teams page. When there is no picture, or the picture fails to load, the initials SHALL be shown. Places that show a person's name as text only SHALL be unchanged.

#### Scenario: Person with a picture

- **WHEN** Alice has a picture and opens Fred
- **THEN** her navigation-rail profile shows the picture, not her initials

#### Scenario: Broken picture link

- **WHEN** the picture URL in Alice's summary fails to load in the browser
- **THEN** her initials are shown in its place

#### Scenario: Administrator avatars on a team card

- **WHEN** a team card lists Alice (with picture) and Bob (without) as administrators
- **THEN** Alice's avatar shows her picture and Bob's shows his initials

### Requirement: Profile picture settings reuse the team avatar experience

The user settings page SHALL offer the same upload card, upload button, preview and square crop dialog as the team avatar settings, with the same client-side file type and size checks. It SHALL additionally offer a Delete action, shown only when a picture exists, that asks for confirmation before deleting. A file refused by the client-side checks, a failed upload and a failed delete SHALL each be reported to the person with an error message, on both the user and the team settings. Team avatar settings SHALL keep their current behaviour otherwise and SHALL NOT gain a delete action.

#### Scenario: Upload through the crop dialog

- **WHEN** Alice picks a valid image on the user settings page and saves the crop
- **THEN** the cropped picture is uploaded and every place showing her avatar updates without a page reload

#### Scenario: Delete with confirmation

- **WHEN** Alice clicks Delete and confirms
- **THEN** her picture is deleted and her initials are shown everywhere

#### Scenario: Delete cancelled

- **WHEN** Alice clicks Delete and cancels the confirmation
- **THEN** her picture is unchanged

#### Scenario: Upload refused by the server

- **WHEN** Alice saves a crop and the server rejects the upload
- **THEN** an error message tells her the image could not be uploaded, with the server's reason when it gives one, and her previous picture is unchanged

#### Scenario: Delete fails

- **WHEN** Alice confirms Delete and the request fails
- **THEN** an error message tells her the picture could not be deleted

#### Scenario: Team avatar settings unchanged

- **WHEN** a team administrator opens team settings
- **THEN** the avatar card offers upload and preview as before, with no Delete action

### Requirement: Profile pictures stay out of exports and telemetry

Platform export SHALL NOT include profile pictures or their keys. Logs, metrics and audit events SHALL NOT contain picture bytes, presigned picture URLs or display names.

#### Scenario: Platform export

- **WHEN** an administrator exports the platform while several people have pictures
- **THEN** the export contains no profile picture data or picture keys

#### Scenario: Upload logging

- **WHEN** Alice uploads a picture
- **THEN** no log line, metric label or audit event contains the image, its presigned URL or her display name
