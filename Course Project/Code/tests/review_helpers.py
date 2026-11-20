def review_all(app, ctx, reviewer='Research Dean'):
    """Explicit fixture reviewer decisions; never part of production approval."""
    for result in ctx.report['faculty_results']:
        app.review_attribution(ctx.run_id, result['faculty']['faculty_id'], 'Fixture author assignments manually checked against the test dataset', reviewer)
        for proposal in result.get('duplicate_proposals', []):
            app.review_duplicate(ctx.run_id, result['faculty']['faculty_id'], proposal['group'], 'confirmed', reviewer)
