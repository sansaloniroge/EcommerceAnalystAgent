# Generates docs/demo.gif. Requires the API running locally with a real
# OpenAI key and the dataset loaded (see README "How to run it").
# Run: vhs docs/demo.tape

Output docs/demo.gif

Set Shell "bash"
Set FontSize 17
Set Width 1200
Set Height 560
Set Theme "Dracula"
Set TypingSpeed 8ms
Set Padding 20

Type "# A question resolved with a real SQL query and a calculator call:"
Enter
Sleep 500ms

Type `curl -s localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "What percentage of all orders have status delivered?"}' | jq '{answer, tools_used: [.trace[].tool]}'`
Enter
Sleep 6s

Type "# A question the dataset genuinely cannot answer:"
Enter
Sleep 500ms

Type `curl -s localhost:8000/ask -H "Content-Type: application/json" -d '{"question": "What was the profit margin on orders in the health_beauty category?"}' | jq '{answer, tools_used: [.trace[].tool]}'`
Enter
Sleep 6s
