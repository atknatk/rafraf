FROM mem0ai/mem0:latest

# Patch: mem0 >=1.0.9 passes response_format kwarg to
# AWSBedrockLLM.generate_response, which does not support it.
# This monkey-patch strips the unsupported kwarg at startup.
COPY bedrock_patch.py /app/bedrock_patch.py

# Inject patch into mem0 entrypoint
ENV MEM0_BEDROCK_PATCH=/app/bedrock_patch.py
