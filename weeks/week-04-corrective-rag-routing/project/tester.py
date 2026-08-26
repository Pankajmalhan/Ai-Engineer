from app.router import SemanticRouter
router = SemanticRouter()

result = router.route("what is 212+21212? and what")
print(f" Strategy: {result.strategy}, Confidence: {result.confidence}, Scores: {result.scores}, Used Default Fallback: {result.used_default_fallback}")

