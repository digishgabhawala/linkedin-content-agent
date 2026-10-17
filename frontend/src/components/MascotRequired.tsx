/** New-post screen before onboarding's second step: a post needs a mascot
 * (a character with a locked hero), made in Character Studio. */
export function MascotRequired() {
  return (
    <div className="post-form">
      <div className="post-panel__heading">
        <p className="post-panel__eyebrow">One more step before your first post</p>
        <h3 id="new-post-heading">Create your mascot first</h3>
        <p>
          Every post is illustrated with your mascot. Create a character in
          Character Studio and lock its hero image, then come back here to start a post.
        </p>
      </div>
      <div className="post-actions">
        <a href="#characters" className="post-button post-button--primary">
          Open Character Studio
        </a>
      </div>
    </div>
  )
}
