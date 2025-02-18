import React, { useState, useEffect } from 'react';
import {
  Box,
  Paper,
  Typography,
  TextField,
  Button,
  Divider,
  Slider,
  CircularProgress
} from '@mui/material';
import { styled, keyframes } from '@mui/material/styles';

// Animation for chat bubbles.
const fadeIn = keyframes`
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
`;

// ChatBubble styled component with a WhatsApp-like style.
const ChatBubble = styled(Paper)(({ theme, sender }) => ({
  padding: theme.spacing(1.5, 2),
  backgroundColor: sender === 'bot' ? '#f5f5f5' : '#dcf8c6',
  border: sender === 'bot' ? '1px solid #ddd' : 'none',
  color: '#333',
  borderRadius: 16,
  maxWidth: '75%',
  animation: `${fadeIn} 0.3s ease-in-out`,
}));

// Define conversation steps (including separate steps for character details).
const STEPS = {
  BEAT: 0,
  BEAT_CONFIRM: 1,
  CHARACTER_NAME: 2,
  CHARACTER_DESCRIPTION: 3,
  SETTING: 4,
  GENRE: 5,
  STYLE: 6,
  CONFIRM: 7,
  GENERATE: 8,
  EXTEND: 9,
};

export default function App() {
  // Conversation state.
  const [step, setStep] = useState(STEPS.BEAT);
  const [data, setData] = useState({
    beats: [],
    characters: [], // Each character: { name, description }
    setting: '',
    genre: '',
    style: '',
  });
  // Temporary state for the current character name.
  const [currentCharName, setCurrentCharName] = useState("");

  // Initial welcome message.
  const initialMessage = `Welcome! I'm ProseGenerator – an AI-powered creative writing assistant built with React, Material‑UI, FastAPI, OpenAI GPT‑4, and Pinecone.
I use cutting‑edge NLP and vector search to transform your ideas into a roughly 1500‑word narrative.
Let's begin! Please enter your first Story Beat.`;

  // Chat messages.
  const [messages, setMessages] = useState([{ sender: 'bot', text: initialMessage }]);
  const [currentPrompt, setCurrentPrompt] = useState("Type your message here...");
  const [userInput, setUserInput] = useState("");
  const [generatedStory, setGeneratedStory] = useState("");

  // Generation control parameters.
  const [temperature, setTemperature] = useState(0.7);
  const [desiredLength, setDesiredLength] = useState(1500);

  /*
    Layout modes:
      - BEFORE generation:
          "both"     → Chat panel occupies 75% of the width and parameters panel occupies 25%.
          "chatOnly" → Only the chat panel is visible.
      - AFTER generation:
          "both"      → Chat panel occupies 67% of the width and generated story occupies 33%.
          "storyOnly" → Only the generated story panel is visible.
  */
  const [layoutMode, setLayoutMode] = useState("both");
  const [loading, setLoading] = useState(false);

  // Debug logging.
  useEffect(() => {
    console.log("Step:", step);
    console.log("Data:", data);
    console.log("Messages:", messages);
    console.log("Generated story exists?", generatedStory !== "");
    console.log("Layout mode:", layoutMode);
  }, [step, data, messages, generatedStory, layoutMode]);

  // Reset conversation.
  const startOver = () => {
    console.log("startOver() called");
    setStep(STEPS.BEAT);
    setData({ beats: [], characters: [], setting: '', genre: '', style: '' });
    setCurrentCharName("");
    setUserInput("");
    setGeneratedStory("");
    setTemperature(0.7);
    setDesiredLength(1500);
    setLayoutMode("both");
    setMessages([{ sender: 'bot', text: initialMessage }]);
    setCurrentPrompt("Type your message here...");
    console.log("After startOver(), step:", STEPS.BEAT);
  };

  // Handler for sending user input.
  const handleSend = async (e) => {
    e.preventDefault();
    const input = userInput.trim();
    if (!input) return;
    console.log("User input:", input);

    // Append the user's message.
    setMessages(prev => [...prev, { sender: 'user', text: input }]);

    // Allow "start over".
    if (input.toLowerCase() === "start over") {
      startOver();
      return;
    }

    // Conversation flow.
    if (step === STEPS.BEAT) {
      setData(prev => ({ ...prev, beats: [...prev.beats, input] }));
      setMessages(prev => [...prev, { sender: 'bot', text: "Beat added. Do you want to add another beat? (yes/no)" }]);
      setCurrentPrompt("Do you want to add another beat? (yes/no)");
      setStep(STEPS.BEAT_CONFIRM);
    } else if (step === STEPS.BEAT_CONFIRM) {
      if (input.toLowerCase() === 'yes') {
        setMessages(prev => [...prev, { sender: 'bot', text: "Please enter your next Story Beat:" }]);
        setCurrentPrompt("Enter your next Story Beat:");
        setStep(STEPS.BEAT);
      } else {
        setMessages(prev => [...prev, { sender: 'bot', text: "Please enter the name of your first character:" }]);
        setCurrentPrompt("Enter character name:");
        setStep(STEPS.CHARACTER_NAME);
      }
    } else if (step === STEPS.CHARACTER_NAME) {
      // Save current character name.
      setCurrentCharName(input);
      setMessages(prev => [...prev, { sender: 'bot', text: "Now enter the character's description:" }]);
      setCurrentPrompt("Enter character description:");
      setStep(STEPS.CHARACTER_DESCRIPTION);
    } else if (step === STEPS.CHARACTER_DESCRIPTION) {
      // Save character details.
      setData(prev => ({
        ...prev,
        characters: [...prev.characters, { name: currentCharName, description: input }]
      }));
      setMessages(prev => [...prev, { sender: 'bot', text: "Character saved. Do you want to add another character? (yes/no)" }]);
      setCurrentPrompt("Add another character? (yes/no)");
      setStep(STEPS.CHARACTERS);
    } else if (step === STEPS.CHARACTERS) {
      if (input.toLowerCase() === 'yes') {
        setMessages(prev => [...prev, { sender: 'bot', text: "Please enter the name of your next character:" }]);
        setCurrentPrompt("Enter character name:");
        setStep(STEPS.CHARACTER_NAME);
      } else {
        setMessages(prev => [...prev, { sender: 'bot', text: "Characters saved. Now, please enter the Setting of your story:" }]);
        setCurrentPrompt("Enter the Setting:");
        setStep(STEPS.SETTING);
      }
    } else if (step === STEPS.SETTING) {
      setData(prev => ({ ...prev, setting: input }));
      setMessages(prev => [...prev, { sender: 'bot', text: "Setting saved. Now, please enter the Genre:" }]);
      setCurrentPrompt("Enter the Genre:");
      setStep(STEPS.GENRE);
    } else if (step === STEPS.GENRE) {
      setData(prev => ({ ...prev, genre: input }));
      setMessages(prev => [...prev, { sender: 'bot', text: "Genre saved. Now, please enter the desired Style:" }]);
      setCurrentPrompt("Enter the Style:");
      setStep(STEPS.STYLE);
    } else if (step === STEPS.STYLE) {
      setData(prev => ({ ...prev, style: input }));
      // Summarize parameters.
      const summary = `All parameters saved.
Beats: ${data.beats.join(", ")}
Characters: ${data.characters.map(c => `${c.name} (${c.description})`).join("; ")}
Setting: ${data.setting}
Genre: ${data.genre}
Style: ${data.style}

Generate your story? (yes/no)`;
      setMessages(prev => [...prev, { sender: 'bot', text: summary }]);
      setCurrentPrompt("Generate your story? (yes/no)");
      setStep(STEPS.CONFIRM);
    } else if (step === STEPS.CONFIRM) {
      if (input.toLowerCase() === 'yes') {
        setMessages(prev => [...prev, { sender: 'bot', text: "Generating your story... Please wait." }]);
        setCurrentPrompt("Generating...");
        setStep(STEPS.GENERATE);
        await generateStory();
      } else {
        setMessages(prev => [...prev, { sender: 'bot', text: "Story generation cancelled. To try again, type 'start over'." }]);
        setCurrentPrompt("");
      }
    }
    setUserInput("");
  };

  // Function to call the backend and generate the story.
  const generateStory = async () => {
    setLoading(true);
    const payload = {
      beats: data.beats,
      characters: data.characters,
      setting: data.setting,
      genre: data.genre,
      style: data.style,
      temperature: temperature,
      approx_word_count: desiredLength
    };
    console.log("generateStory() payload:", payload);
    try {
      const res = await fetch("http://localhost:8000/generate-prose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await res.json();
      setGeneratedStory(result.prose_output);
      setMessages(prev => [...prev, { sender: 'bot', text: "Story generated. To view the full story, use the toggle button. Type 'start over' to reset." }]);
      setCurrentPrompt("Type your next input:");
      setStep(STEPS.EXTEND);
      setLayoutMode("both");
    } catch (error) {
      console.error("Error generating story:", error);
      setMessages(prev => [...prev, { sender: 'bot', text: "Error generating story. Please try again or type 'start over'." }]);
      setCurrentPrompt("");
    }
    setLoading(false);
  };

  // Central Toggle Button handler.
  const cycleLayoutMode = () => {
    if (generatedStory === "") {
      setLayoutMode(prev => (prev === "both" ? "chatOnly" : "both"));
    } else {
      setLayoutMode(prev => (prev === "both" ? "storyOnly" : "both"));
    }
  };

  // Determine panel widths.
  let leftPanelWidth, rightPanelWidth;
  const beforeGeneration = generatedStory === "";
  if (beforeGeneration) {
    if (layoutMode === "chatOnly") {
      leftPanelWidth = "100%";
      rightPanelWidth = 0;
    } else {
      leftPanelWidth = "75%";
      rightPanelWidth = "25%";
    }
  } else {
    if (layoutMode === "storyOnly") {
      leftPanelWidth = 0;
      rightPanelWidth = "100%";
    } else {
      leftPanelWidth = "67%";
      rightPanelWidth = "33%";
    }
  }
  const chatVisible = beforeGeneration ? true : (layoutMode !== "storyOnly");
  const rightVisible = rightPanelWidth !== 0;

  return (
    <Box
      sx={{
        width: "100vw",
        height: "100vh",
        p: 2,
        background: "#f0f2f5",
        boxSizing: "border-box",
        overflow: "hidden",
        display: "flex",
        gap: 2,
      }}
    >
      {/* Loading Overlay */}
      {loading && (
        <Box
          sx={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(0,0,0,0.5)",
            zIndex: 200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <CircularProgress size={80} color="inherit" />
        </Box>
      )}

      {/* Chat Panel */}
      {chatVisible && (
        <Box
          sx={{
            flexBasis: leftPanelWidth,
            height: "100%",
            display: "flex",
            flexDirection: "column",
            border: "1px solid #ccc",
            borderRadius: 2,
            overflow: "hidden",
            background: "#fff",
          }}
        >
          <Typography variant="h5" sx={{ p: 2, fontWeight: "bold" }}>
            Chat with ProseGenerator
          </Typography>
          {/* Messages container: latest 3 messages */}
          <Box
            sx={{
              flexGrow: 1,
              overflowY: "auto",
              p: 2,
              minHeight: 0,
            }}
          >
            {messages.slice(-3).map((msg, index) => (
              <Box
                key={index}
                sx={{
                  display: "flex",
                  justifyContent: msg.sender === "bot" ? "flex-start" : "flex-end",
                  mb: 1,
                }}
              >
                <ChatBubble sender={msg.sender}>
                  <Typography variant="body1" sx={{ fontSize: "1.3rem" }}>
                    {msg.text}
                  </Typography>
                </ChatBubble>
              </Box>
            ))}
          </Box>
          {/* Input area */}
          <Box component="form" onSubmit={handleSend} sx={{ p: 2, display: "flex", gap: 1 }}>
            <TextField
              fullWidth
              multiline
              minRows={3}
              variant="outlined"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder={currentPrompt}
              sx={{ background: "#fff", borderRadius: 2 }}
              InputProps={{ sx: { fontSize: "1.3rem", px: 2, py: 1 } }}
              required
            />
            <Button type="submit" variant="contained" color="primary">
              Send
            </Button>
          </Box>
        </Box>
      )}

      {/* Parameters / Generated Story Panel */}
      {rightVisible && (
        <Box
          sx={{
            flexBasis: rightPanelWidth,
            height: "100%",
            display: "flex",
            flexDirection: "column",
            border: "1px solid #ccc",
            borderRadius: 2,
            overflow: "hidden",
            background: "#fff",
          }}
        >
          {beforeGeneration ? (
            <>
              <Typography variant="h6" sx={{ p: 2, fontWeight: "bold" }}>
                Generation Parameters
              </Typography>
              <Box sx={{ p: 2 }}>
                <Typography variant="body1">Temperature: {temperature.toFixed(2)}</Typography>
                <Slider
                  value={temperature}
                  onChange={(e, newValue) => setTemperature(newValue)}
                  min={0}
                  max={1}
                  step={0.05}
                  valueLabelDisplay="auto"
                />
              </Box>
              <Box sx={{ p: 2 }}>
                <Typography variant="body1">Desired Word Count: {desiredLength}</Typography>
                <Slider
                  value={desiredLength}
                  onChange={(e, newValue) => setDesiredLength(newValue)}
                  min={1500}
                  max={2500}
                  step={50}
                  valueLabelDisplay="auto"
                />
              </Box>
              <Box sx={{ p: 2 }}>
                <Typography variant="body2">
                  Adjust the parameters above before generating your story.
                </Typography>
              </Box>
            </>
          ) : (
            <>
              <Typography variant="h6" sx={{ p: 2, fontWeight: "bold" }}>
                Generated Story
              </Typography>
              <Divider />
              {/* Flex container to fill available space and allow full scrolling */}
              <Box
                sx={{
                  flexGrow: 1,
                  minHeight: 0,
                  overflowY: "auto",
                  p: 2,
                }}
              >
                <Typography variant="body1" sx={{ whiteSpace: "pre-line", lineHeight: 1.6 }}>
                  {generatedStory}
                </Typography>
              </Box>
            </>
          )}
        </Box>
      )}
    </Box>
  );
}
