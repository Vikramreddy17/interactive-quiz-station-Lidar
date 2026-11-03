# question_provider.py
"""
Quiz Arena - Question Provider
Retrieves questions from The Trivia API with category and difficulty filtering,
maintains question cache and history, limits repeat questions,
and ensures perfectly balanced correct answer distribution (5 A's, 5 B's, 5 C's, 5 D's).
"""

import json
import os
import random
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
CACHE_FILE = DATA / "question_cache.json"
HISTORY_FILE = DATA / "question_history.json"

API_URL = "https://the-trivia-api.com/v2/questions"
API_KEY = os.environ.get("TRIVIA_API_KEY", "").strip()

QUESTION_COUNT = 20
TIME_LIMIT = 15
MAX_REPEATS = 5
FETCH_ROUNDS = 5
LOCK = threading.RLock()

DIFFICULTIES = {
    "easy": "Easy",
    "medium": "Medium",
    "hard": "Hard",
}

CATEGORIES = {
    "tech": {
        "name": "Tech & Innovation",
        "api_categories": ["science"],
    },
    "design": {
        "name": "Design & Creativity",
        "api_categories": ["arts_and_literature"],
    },
    "general": {
        "name": "World & Wonders",
        "api_categories": ["general_knowledge", "geography", "history"],
    },
}

# ============================================================================
# BUILT-IN FALLBACK QUESTIONS (Ensures zero-downtime offline gameplay)
# ============================================================================
FALLBACK_QUESTIONS = {
    "tech": {
        "easy": [
            {"id": "t_e_1", "question": "What does 'CPU' stand for in computer science?", "correctAnswer": "Central Processing Unit", "incorrectAnswers": ["Computer Personal Unit", "Central Power Unit", "Core Processing Utility"]},
            {"id": "t_e_2", "question": "Which company developed the Android mobile operating system?", "correctAnswer": "Google", "incorrectAnswers": ["Apple", "Microsoft", "Samsung"]},
            {"id": "t_e_3", "question": "What does 'HTML' stand for?", "correctAnswer": "HyperText Markup Language", "incorrectAnswers": ["HighText Machine Language", "Hyperlink Text Mode Language", "Home Tool Markup Language"]},
            {"id": "t_e_4", "question": "Which key combination is universally used to copy text in Windows?", "correctAnswer": "Ctrl + C", "incorrectAnswers": ["Ctrl + V", "Ctrl + X", "Ctrl + Z"]},
            {"id": "t_e_5", "question": "What is the primary function of RAM in a computer?", "correctAnswer": "Temporary short-term memory", "incorrectAnswers": ["Permanent file storage", "Graphics rendering", "Power management"]},
            {"id": "t_e_6", "question": "Who is known as the co-founder of Microsoft alongside Paul Allen?", "correctAnswer": "Bill Gates", "incorrectAnswers": ["Steve Jobs", "Elon Musk", "Jeff Bezos"]},
            {"id": "t_e_7", "question": "Which device connects computers together within a local network?", "correctAnswer": "Router", "incorrectAnswers": ["Monitor", "Power Supply", "Heatsink"]},
            {"id": "t_e_8", "question": "What does 'WWW' stand for in website addresses?", "correctAnswer": "World Wide Web", "incorrectAnswers": ["World Wireless Web", "Wide World Wave", "Web World Wide"]},
            {"id": "t_e_9", "question": "Which company created the iPhone and Mac computers?", "correctAnswer": "Apple", "incorrectAnswers": ["IBM", "Sony", "Dell"]},
            {"id": "t_e_10", "question": "What is a single binary digit (0 or 1) called?", "correctAnswer": "Bit", "incorrectAnswers": ["Byte", "Nibble", "Pixel"]},
            {"id": "t_e_11", "question": "Which programming language is named after a British comedy troupe?", "correctAnswer": "Python", "incorrectAnswers": ["Java", "Ruby", "Perl"]},
            {"id": "t_e_12", "question": "What does 'USB' stand for?", "correctAnswer": "Universal Serial Bus", "incorrectAnswers": ["Unified System Board", "Universal Storage Byte", "Ultra Speed Bus"]},
            {"id": "t_e_13", "question": "Which popular web browser is developed by Google?", "correctAnswer": "Chrome", "incorrectAnswers": ["Firefox", "Safari", "Edge"]},
            {"id": "t_e_14", "question": "What type of computer display uses liquid crystals?", "correctAnswer": "LCD", "incorrectAnswers": ["CRT", "OLED", "Plasma"]},
            {"id": "t_e_15", "question": "What is the name of the battery used to keep BIOS time running?", "correctAnswer": "CMOS Battery", "incorrectAnswers": ["AA Battery", "Lithium Core", "RAM Cell"]},
            {"id": "t_e_16", "question": "Which sensor in smartphones detects the orientation of the screen?", "correctAnswer": "Accelerometer", "incorrectAnswers": ["Barometer", "Thermometer", "Hygrometer"]},
            {"id": "t_e_17", "question": "What does 'GPU' stand for?", "correctAnswer": "Graphics Processing Unit", "incorrectAnswers": ["General Power Unit", "Gaming Performance Utility", "Global Pixel Unit"]},
            {"id": "t_e_18", "question": "Which technology allows wireless communication over short distances between phones?", "correctAnswer": "NFC", "incorrectAnswers": ["GPS", "LTE", "Satellite"]},
            {"id": "t_e_19", "question": "What symbol is used at the start of an email address domain?", "correctAnswer": "@", "incorrectAnswers": ["#", "$", "&"]},
            {"id": "t_e_20", "question": "Which storage device has no moving mechanical parts?", "correctAnswer": "Solid State Drive (SSD)", "incorrectAnswers": ["Hard Disk Drive (HDD)", "Floppy Disk", "Optical Disc"]}
        ],
        "medium": [
            {"id": "t_m_1", "question": "In networking, what does DNS stand for?", "correctAnswer": "Domain Name System", "incorrectAnswers": ["Data Network Service", "Dynamic Network Storage", "Domain Node Server"]},
            {"id": "t_m_2", "question": "Which data structure operates on a 'First-In, First-Out' (FIFO) basis?", "correctAnswer": "Queue", "incorrectAnswers": ["Stack", "Binary Tree", "Hash Map"]},
            {"id": "t_m_3", "question": "What port number is standard for unencrypted HTTP web traffic?", "correctAnswer": "80", "incorrectAnswers": ["443", "22", "8080"]},
            {"id": "t_m_4", "question": "What does the term 'LiDAR' stand for?", "correctAnswer": "Light Detection and Ranging", "incorrectAnswers": ["Laser Intensity Digital Radar", "Linear Data Radio", "Light Distance Array"]},
            {"id": "t_m_5", "question": "Which encryption protocol secures standard HTTPS connections?", "correctAnswer": "TLS / SSL", "incorrectAnswers": ["FTP", "SNMP", "SMTP"]},
            {"id": "t_m_6", "question": "What is the computational complexity of binary search on a sorted list?", "correctAnswer": "O(log n)", "incorrectAnswers": ["O(n)", "O(n^2)", "O(1)"]},
            {"id": "t_m_7", "question": "Who created the Linux operating system kernel in 1991?", "correctAnswer": "Linus Torvalds", "incorrectAnswers": ["Richard Stallman", "Dennis Ritchie", "Ken Thompson"]},
            {"id": "t_m_8", "question": "In database design, what does 'SQL' stand for?", "correctAnswer": "Structured Query Language", "incorrectAnswers": ["Sequential Query Logic", "Standard Question List", "System Query Link"]},
            {"id": "t_m_9", "question": "Which transmission protocol is connectionless and does not guarantee packet delivery?", "correctAnswer": "UDP", "incorrectAnswers": ["TCP", "BGP", "SCTP"]},
            {"id": "t_m_10", "question": "What is the primary role of an operating system kernel?", "correctAnswer": "Bridge between software and hardware resources", "incorrectAnswers": ["Compile user source code", "Render graphic interfaces", "Encrypt files on disk"]},
            {"id": "t_m_11", "question": "Which IEEE standard governs standard Wi-Fi wireless networks?", "correctAnswer": "802.11", "incorrectAnswers": ["802.3", "802.15", "802.16"]},
            {"id": "t_m_12", "question": "In Python, which built-in function returns the memory address of an object?", "correctAnswer": "id()", "incorrectAnswers": ["hex()", "mem()", "address()"]},
            {"id": "t_m_13", "question": "What does RAID 1 provide in data storage configurations?", "correctAnswer": "Disk Mirroring", "incorrectAnswers": ["Disk Striping", "Parity with Striping", "Block-level Encryption"]},
            {"id": "t_m_14", "question": "Which company originally invented the JavaScript programming language at Netscape?", "correctAnswer": "Brendan Eich", "incorrectAnswers": ["James Gosling", "Guido van Rossum", "Bjarne Stroustrup"]},
            {"id": "t_m_15", "question": "What does 'IoT' stand for in modern embedded computing?", "correctAnswer": "Internet of Things", "incorrectAnswers": ["Interface of Technology", "Internal Output Terminal", "Intelligent Online Tools"]},
            {"id": "t_m_16", "question": "In version control with Git, which command creates an isolated work branch?", "correctAnswer": "git checkout -b", "incorrectAnswers": ["git merge", "git push", "git init"]},
            {"id": "t_m_17", "question": "What is the default subnet mask for a standard Class C IPv4 network?", "correctAnswer": "255.255.255.0", "incorrectAnswers": ["255.0.0.0", "255.255.0.0", "255.255.255.255"]},
            {"id": "t_m_18", "question": "Which algorithm is commonly used for public-key asymmetric cryptography?", "correctAnswer": "RSA", "incorrectAnswers": ["AES", "DES", "Blowfish"]},
            {"id": "t_m_19", "question": "What is the purpose of Docker containers in modern DevOps?", "correctAnswer": "Package code with dependencies in isolated environments", "incorrectAnswers": ["Simulate whole physical CPU hardware", "Replace network switches", "Manage server power supplies"]},
            {"id": "t_m_20", "question": "Which logic gate outputs TRUE only when both inputs differ?", "correctAnswer": "XOR", "incorrectAnswers": ["AND", "OR", "NAND"]}
        ],
        "hard": [
            {"id": "t_h_1", "question": "Which Byzantine fault tolerant consensus mechanism was introduced in Bitcoin?", "correctAnswer": "Proof of Work (Nakamoto Consensus)", "incorrectAnswers": ["Proof of Stake", "Raft", "Paxos"]},
            {"id": "t_h_2", "question": "In microprocessor design, what does 'SIMD' architecture stand for?", "correctAnswer": "Single Instruction, Multiple Data", "incorrectAnswers": ["Sequential Instruction, Multiple Devices", "Synchronized Interface, Modular Drive", "Silicon Integrated Micro Device"]},
            {"id": "t_h_3", "question": "What mathematical problem underpins the security of classic Diffie-Hellman key exchange?", "correctAnswer": "Discrete Logarithm Problem", "incorrectAnswers": ["Prime Factorization of Semiprimes", "Shortest Vector Problem", "Traveling Salesman Problem"]},
            {"id": "t_h_4", "question": "In Linux memory management, what is the standard base virtual page size on x86-64?", "correctAnswer": "4 Kilobytes", "incorrectAnswers": ["2 Megabytes", "1 Kilobyte", "64 Kilobytes"]},
            {"id": "t_h_5", "question": "Which theorem states that a distributed data store can only guarantee 2 of 3 core properties?", "correctAnswer": "CAP Theorem", "incorrectAnswers": ["Shannon-Hartley Theorem", "Amdahl's Law", "Cook's Theorem"]},
            {"id": "t_h_6", "question": "What is the name of the cache coherence protocol used in multi-core CPUs (MESI)?", "correctAnswer": "Modified, Exclusive, Shared, Invalid", "incorrectAnswers": ["Memory, Extended, Serial, Internal", "Modular, Encrypted, Synchronous, Indexed", "Multiplexed, Electronic, State, Interleaved"]},
            {"id": "t_h_7", "question": "In quantum computing, what property allows qubits to remain linked regardless of distance?", "correctAnswer": "Quantum Entanglement", "incorrectAnswers": ["Superposition", "Wave Collapse", "Quantum Annealing"]},
            {"id": "t_h_8", "question": "What is the maximum payload size of a standard unfragmented Ethernet MTU frame?", "correctAnswer": "1500 bytes", "incorrectAnswers": ["1024 bytes", "2048 bytes", "9000 bytes"]},
            {"id": "t_h_9", "question": "Which CPU vulnerability exploited speculative execution via branch prediction cache timings?", "correctAnswer": "Spectre", "incorrectAnswers": ["Heartbleed", "Shellshock", "Stuxnet"]},
            {"id": "t_h_10", "question": "In database transactions, what does the 'I' represent in ACID properties?", "correctAnswer": "Isolation", "incorrectAnswers": ["Integrity", "Iteration", "Idempotence"]},
            {"id": "t_h_11", "question": "Which sorting algorithm has the worst-case time complexity of O(n^2) but O(n log n) average?", "correctAnswer": "Quicksort", "incorrectAnswers": ["Mergesort", "Heapsort", "Timsort"]},
            {"id": "t_h_12", "question": "In compiler theory, what does 'AST' stand for?", "correctAnswer": "Abstract Syntax Tree", "incorrectAnswers": ["Automated Semantic Token", "Assembly Source Table", "Algorithmic State Transition"]},
            {"id": "t_h_13", "question": "What is the wavelength commonly used in short-range pulsed LiDAR sensors like LD19?", "correctAnswer": "905 nanometers (Near-Infrared)", "incorrectAnswers": ["532 nanometers (Green)", "1550 nanometers (SWIR)", "650 nanometers (Red)"]},
            {"id": "t_h_14", "question": "Which data structure uses multiple randomized linked lists to achieve O(log n) lookups?", "correctAnswer": "Skip List", "incorrectAnswers": ["B-Tree", "Radix Tree", "Bloom Filter"]},
            {"id": "t_h_15", "question": "In neural networks, what technique mitigates vanishing gradients by keeping residual connections?", "correctAnswer": "ResNet (Skip Connections)", "incorrectAnswers": ["Dropout", "Softmax", "Batch Normalization"]},
            {"id": "t_h_16", "question": "What is the theoretical maximum baud rate of standard RS-232 serial over long cables?", "correctAnswer": "115200 bps", "incorrectAnswers": ["10 Mbps", "480 Mbps", "1 Gbps"]},
            {"id": "t_h_17", "question": "Which consensus protocol is widely known for simplicity and understanding compared to Paxos?", "correctAnswer": "Raft", "incorrectAnswers": ["Zab", "Chubby", "Tendermint"]},
            {"id": "t_h_18", "question": "What memory barrier instruction prevents CPU reordering of read and write cycles?", "correctAnswer": "Memory Fence (MFENCE)", "incorrectAnswers": ["NOP", "RET", "JMP"]},
            {"id": "t_h_19", "question": "In relational databases, which normal form eliminates transitive functional dependencies?", "correctAnswer": "Third Normal Form (3NF)", "incorrectAnswers": ["First Normal Form (1NF)", "Second Normal Form (2NF)", "Boyce-Codd Normal Form"]},
            {"id": "t_h_20", "question": "Which cryptographic hash function family was selected by NIST as SHA-3 (Keccak)?", "correctAnswer": "Sponge Construction", "incorrectAnswers": ["Merkle-Damgård", "Feistel Network", "Substitution-Permutation"]}
        ]
    },
    "design": {
        "easy": [
            {"id": "d_e_1", "question": "Which primary colors are used in digital screen displays?", "correctAnswer": "Red, Green, Blue (RGB)", "incorrectAnswers": ["Cyan, Magenta, Yellow", "Red, Yellow, Blue", "Black, White, Gray"]},
            {"id": "d_e_2", "question": "What do we call the empty space around elements in graphic design?", "correctAnswer": "Negative Space / White Space", "incorrectAnswers": ["Dead Canvas", "Null Margin", "Shadow Gap"]},
            {"id": "d_e_3", "question": "Which famous art style did Pablo Picasso co-found?", "correctAnswer": "Cubism", "incorrectAnswers": ["Surrealism", "Impressionism", "Baroque"]},
            {"id": "d_e_4", "question": "What is the term for fonts that feature small decorative strokes at the ends of letters?", "correctAnswer": "Serif", "incorrectAnswers": ["Sans-Serif", "Monospace", "Script"]},
            {"id": "d_e_5", "question": "Who painted the famous masterpiece 'Mona Lisa'?", "correctAnswer": "Leonardo da Vinci", "incorrectAnswers": ["Michelangelo", "Vincent van Gogh", "Raphael"]},
            {"id": "d_e_6", "question": "In color theory, what color is directly opposite blue on the standard color wheel?", "correctAnswer": "Orange", "incorrectAnswers": ["Red", "Green", "Purple"]},
            {"id": "d_e_7", "question": "What does 'UI' stand for in digital product design?", "correctAnswer": "User Interface", "incorrectAnswers": ["User Intelligence", "Universal Information", "Unified Interaction"]},
            {"id": "d_e_8", "question": "Which color mode is universally used for four-color professional print production?", "correctAnswer": "CMYK", "incorrectAnswers": ["RGB", "HEX", "HSL"]},
            {"id": "d_e_9", "question": "What is the name of Vincent van Gogh's famous swirling night sky painting?", "correctAnswer": "The Starry Night", "incorrectAnswers": ["Sunflowers", "The Night Café", "Bedroom in Arles"]},
            {"id": "d_e_10", "question": "Which file format supports transparent vector graphics on the web?", "correctAnswer": "SVG", "incorrectAnswers": ["JPEG", "BMP", "TIFF"]},
            {"id": "d_e_11", "question": "What design principle ensures visual elements feel stable and evenly distributed?", "correctAnswer": "Balance", "incorrectAnswers": ["Contrast", "Saturation", "Kerning"]},
            {"id": "d_e_12", "question": "What famous German art and design school operated from 1919 to 1933?", "correctAnswer": "Bauhaus", "incorrectAnswers": ["De Stijl", "Art Nouveau", "Futurism"]},
            {"id": "d_e_13", "question": "What do we call the spacing between specific pairs of letters in typography?", "correctAnswer": "Kerning", "incorrectAnswers": ["Leading", "Tracking", "Alignment"]},
            {"id": "d_e_14", "question": "Which design software created by Adobe is famous for vector illustration?", "correctAnswer": "Illustrator", "incorrectAnswers": ["Photoshop", "Premiere", "Audition"]},
            {"id": "d_e_15", "question": "What is a monochromatic color scheme composed of?", "correctAnswer": "Variations of a single hue with tints and shades", "incorrectAnswers": ["Three adjacent colors", "Complementary opposites", "Pure black and white only"]},
            {"id": "d_e_16", "question": "Who sculpted the famous marble statue of 'David' in Florence?", "correctAnswer": "Michelangelo", "incorrectAnswers": ["Donatello", "Bernini", "Rodin"]},
            {"id": "d_e_17", "question": "What is the horizontal guideline on which most text characters sit?", "correctAnswer": "Baseline", "incorrectAnswers": ["Mean line", "Cap height", "Ascender line"]},
            {"id": "d_e_18", "question": "What does 'UX' stand for in software and interaction design?", "correctAnswer": "User Experience", "incorrectAnswers": ["Unified Extension", "Utility Exchange", "User Exploration"]},
            {"id": "d_e_19", "question": "Which famous painting depicts a figure holding their face in agony against an orange sky?", "correctAnswer": "The Scream (Edvard Munch)", "incorrectAnswers": ["Guernica", "The Kiss", "American Gothic"]},
            {"id": "d_e_20", "question": "What design compositional rule divides an image into nine equal parts using two horizontal and two vertical lines?", "correctAnswer": "Rule of Thirds", "incorrectAnswers": ["Golden Ratio", "Diagonal Method", "Symmetry Principle"]}
        ],
        "medium": [
            {"id": "d_m_1", "question": "What is the numerical approximation of the Golden Ratio (Phi) used in classical aesthetics?", "correctAnswer": "1.618", "incorrectAnswers": ["1.414", "3.141", "2.718"]},
            {"id": "d_m_2", "question": "In typography, what term describes the vertical space between lines of text?", "correctAnswer": "Leading", "incorrectAnswers": ["Tracking", "Kerning", "Ascent"]},
            {"id": "d_m_3", "question": "Which design philosophy famously coined the motto 'Less is more'?", "correctAnswer": "Minimalism (Ludwig Mies van der Rohe)", "incorrectAnswers": ["Postmodernism", "Brutalism", "Art Deco"]},
            {"id": "d_m_4", "question": "Which influential industrial designer formulated the 'Ten Principles for Good Design' at Braun?", "correctAnswer": "Dieter Rams", "incorrectAnswers": ["Jony Ive", "Philippe Starck", "Charles Eames"]},
            {"id": "d_m_5", "question": "In Gestalt psychology of perception, which principle explains why minds group nearby objects?", "correctAnswer": "Proximity", "incorrectAnswers": ["Continuity", "Closure", "Symmetry"]},
            {"id": "d_m_6", "question": "What is the term for a design mockup that demonstrates interactive state and navigation without final code?", "correctAnswer": "Interactive Prototype", "incorrectAnswers": ["Moodboard", "Style Tile", "Design Matrix"]},
            {"id": "d_m_7", "question": "Which Dutch movement, led by Piet Mondrian, championed primary colors and black grid lines?", "correctAnswer": "De Stijl", "incorrectAnswers": ["Dadaism", "Suprematism", "Constructivism"]},
            {"id": "d_m_8", "question": "What is the optical difference between font 'Tracking' and font 'Kerning'?", "correctAnswer": "Tracking adjusts uniform space across all characters; kerning adjusts between two specific letters", "incorrectAnswers": ["Tracking changes font height; kerning changes width", "Kerning is for headers only", "Tracking is used exclusively in serif fonts"]},
            {"id": "d_m_9", "question": "In user interface heuristics, what is 'Affordance'?", "correctAnswer": "A property that signals how an object or control should be used", "incorrectAnswers": ["The total cost of developing a UI", "The download size of screen assets", "The color contrast ratio of text"]},
            {"id": "d_m_10", "question": "What is the minimum WCAG 2.1 Level AA color contrast ratio required for normal body text?", "correctAnswer": "4.5 : 1", "incorrectAnswers": ["3 : 1", "7 : 1", "2 : 1"]},
            {"id": "d_m_11", "question": "Which typeface designed by Max Miedinger and Eduard Hoffmann in 1957 became a global standard?", "correctAnswer": "Helvetica", "incorrectAnswers": ["Futura", "Garamond", "Times New Roman"]},
            {"id": "d_m_12", "question": "What architectural and graphic movement was characterized by raw exposed concrete and geometric block forms?", "correctAnswer": "Brutalism", "incorrectAnswers": ["Art Nouveau", "Rococo", "Memphis Design"]},
            {"id": "d_m_13", "question": "Which color harmony combines one base color and the two colors adjacent to its complement?", "correctAnswer": "Split-Complementary", "incorrectAnswers": ["Triadic", "Tetradic", "Analogous"]},
            {"id": "d_m_14", "question": "In digital audio and spatial design, what is an 'Interactive Touch Zone'?", "correctAnswer": "A designated physical or virtual coordinate area responding to touch gestures", "incorrectAnswers": ["A sound dampening panel", "A projector cooling boundary", "An ambient lighting threshold"]},
            {"id": "d_m_15", "question": "What does 'Skeuomorphism' refer to in graphic UI design?", "correctAnswer": "Making digital elements mimic the appearance and texture of real-world physical objects", "incorrectAnswers": ["Flat minimalist geometry", "Neon glowing outlines", "Isometric 3D illustrations"]},
            {"id": "d_m_16", "question": "Who designed the iconic Lounge Chair and Ottoman for Herman Miller in 1956?", "correctAnswer": "Charles and Ray Eames", "incorrectAnswers": ["Eero Saarinen", "Isamu Noguchi", "Marcel Breuer"]},
            {"id": "d_m_17", "question": "What is the term for visual tension created when elements of different visual weights sit against each other?", "correctAnswer": "Contrast", "incorrectAnswers": ["Harmony", "Rhythm", "Scale"]},
            {"id": "d_m_18", "question": "In digital typography, what is the 'X-Height' of a typeface?", "correctAnswer": "The height of lowercase letters excluding ascenders and descenders", "incorrectAnswers": ["The total height of capital X", "The line height multiplier", "The width of the widest character"]},
            {"id": "d_m_19", "question": "Which Italian design group founded by Ettore Sottsass in 1980 was famous for colorful geometric post-modern furniture?", "correctAnswer": "The Memphis Group", "incorrectAnswers": ["Alessi", "Kartell", "Studio Alchimia"]},
            {"id": "d_m_20", "question": "In responsive digital design, what is a 'Breakpoint'?", "correctAnswer": "A specific screen width where the layout shifts to optimize viewing", "incorrectAnswers": ["A point where code execution halts", "A line break inside a paragraph", "The maximum file size for web graphics"]}
        ],
        "hard": [
            {"id": "d_h_1", "question": "What is the psychological law stating that reaction time increases logarithmically with the number of choices?", "correctAnswer": "Hick's Law", "incorrectAnswers": ["Fitts's Law", "Miller's Law", "Jakob's Law"]},
            {"id": "d_h_2", "question": "Which ergonomic law models the time required to rapidly move to a target area based on distance and size?", "correctAnswer": "Fitts's Law", "incorrectAnswers": ["Weber-Fechner Law", "Taylor's Theorem", "Pareto Principle"]},
            {"id": "d_h_3", "question": "What is the term for the optical correction where rounded letterforms (like O, C, S) extend slightly beyond baseline and cap-height?", "correctAnswer": "Overshoot", "incorrectAnswers": ["Ligature", "Kerning Offset", "Tittle Drift"]},
            {"id": "d_h_4", "question": "In colorimetry, which color space was designed to be perceptually uniform to human eyesight?", "correctAnswer": "CIELAB (L*a*b*)", "incorrectAnswers": ["sRGB", "Adobe RGB", "YUV"]},
            {"id": "d_h_5", "question": "Who authored the seminal 1988 book 'The Design of Everyday Things' introducing affordances and signifiers?", "correctAnswer": "Don Norman", "incorrectAnswers": ["Jakob Nielsen", "Alan Cooper", "Steve Krug"]},
            {"id": "d_h_6", "question": "What is the name of the typographic character formed by joining two adjacent glyphs (such as 'fi' or 'fl')?", "correctAnswer": "Ligature", "incorrectAnswers": ["Serif", "Diacritic", "Glyph Accent"]},
            {"id": "d_h_7", "question": "In interaction design, what cognitive principle states humans remember roughly 7 plus or minus 2 chunks of information?", "correctAnswer": "Miller's Law", "incorrectAnswers": ["Zipf's Law", "Hebb's Rule", "Dunbar's Number"]},
            {"id": "d_h_8", "question": "Which legendary graphic designer created iconic corporate identities for IBM, ABC, UPS, and Westinghouse?", "correctAnswer": "Paul Rand", "incorrectAnswers": ["Saul Bass", "Milton Glaser", "Massimo Vignelli"]},
            {"id": "d_h_9", "question": "What is the primary optical reason digital interactive installations experience 'Parallax Error' with projectors and touch planes?", "correctAnswer": "Angular offset between the user's line of sight and the physical touch detection plane", "incorrectAnswers": ["Latency in the serial communication baud rate", "Projector bulb heat expansion", "Ambient fluorescent light interference"]},
            {"id": "d_h_10", "question": "In exhibition and spatial design, what is 'Wayfinding'?", "correctAnswer": "The architectural and graphic spatial cues that help people navigate a physical environment", "incorrectAnswers": ["The method of calculating projector throw ratio", "Calibrating LiDAR sensor baud rates", "Designing wireframes for mobile screens"]},
            {"id": "d_h_11", "question": "Which printing defect occurs when two misaligned repetitive halftone screen patterns produce an unwanted wavy interference?", "correctAnswer": "Moiré Effect", "incorrectAnswers": ["Trapping Error", "Dot Gain", "Bleed Banding"]},
            {"id": "d_h_12", "question": "Who designed the landmark 1972 modernist New York City Subway Map and the American Airlines corporate identity?", "correctAnswer": "Massimo Vignelli", "incorrectAnswers": ["Erik Spiekermann", "Paula Scher", "David Carson"]},
            {"id": "d_h_13", "question": "What is the term for subtle horizontal guidelines placed under letter counters to prevent visual ink clogging in small type?", "correctAnswer": "Ink Traps", "incorrectAnswers": ["Serifs", "Counterweights", "Baselines"]},
            {"id": "d_h_14", "question": "In spatial human-computer interaction, what is the 'Reach Envelope'?", "correctAnswer": "The 3D physical volume accessible to a user's arm and hand without bending the torso", "incorrectAnswers": ["The maximum laser distance of a LiDAR scan", "The focal length of an ultra-short throw projector", "The bounding box of a touchscreen monitor"]},
            {"id": "d_h_15", "question": "What cognitive bias causes users to perceive aesthetically pleasing designs as more usable and bug-free?", "correctAnswer": "Aesthetic-Usability Effect", "incorrectAnswers": ["Halo Effect", "Confirmation Bias", "Von Restorff Effect"]},
            {"id": "d_h_16", "question": "Which influential art movement, founded by Filippo Tommaso Marinetti in 1909, glorified velocity, machinery, and industrial technology?", "correctAnswer": "Futurism", "incorrectAnswers": ["Vorticism", "Constructivism", "Art Deco"]},
            {"id": "d_h_17", "question": "In graphic printing, what is the term for extending the background color beyond the trim edge to prevent white margins after cutting?", "correctAnswer": "Bleed", "incorrectAnswers": ["Slug", "Trim Margin", "Crop Allowance"]},
            {"id": "d_h_18", "question": "What is the typographic term for a very short line or single word stranded at the end of a paragraph or top of a column?", "correctAnswer": "Orphan / Widow", "incorrectAnswers": ["Drop Cap", "Folio", "Run-in Header"]},
            {"id": "d_h_19", "question": "In display technology, what is the 'Weber-Fechner Law' used to calculate regarding backlight perception?", "correctAnswer": "Human perception of screen brightness is logarithmic rather than linear", "incorrectAnswers": ["Refresh rate limits human eye tracking", "Pixel density diminishes with viewing angle", "Contrast reduces in bright ambient sunlight"]},
            {"id": "d_h_20", "question": "Which 19th-century British movement led by William Morris championed handmade craftsmanship against soulless industrial manufacturing?", "correctAnswer": "Arts and Crafts Movement", "incorrectAnswers": ["Pre-Raphaelite Brotherhood", "Art Nouveau", "Romanticism"]}
        ]
    },
    "general": {
        "easy": [
            {"id": "g_e_1", "question": "What is the capital city of France?", "correctAnswer": "Paris", "incorrectAnswers": ["London", "Rome", "Madrid"]},
            {"id": "g_e_2", "question": "Which planet in our solar system is known as the 'Red Planet'?", "correctAnswer": "Mars", "incorrectAnswers": ["Venus", "Jupiter", "Saturn"]},
            {"id": "g_e_3", "question": "What is the chemical formula for pure water?", "correctAnswer": "H2O", "incorrectAnswers": ["CO2", "NaCl", "O2"]},
            {"id": "g_e_4", "question": "How many continents are there on planet Earth?", "correctAnswer": "7", "incorrectAnswers": ["5", "6", "8"]},
            {"id": "g_e_5", "question": "Which ocean is the largest and deepest on Earth?", "correctAnswer": "Pacific Ocean", "incorrectAnswers": ["Atlantic Ocean", "Indian Ocean", "Arctic Ocean"]},
            {"id": "g_e_6", "question": "Who was the first human to walk on the Moon in 1969?", "correctAnswer": "Neil Armstrong", "incorrectAnswers": ["Buzz Aldrin", "Yuri Gagarin", "Michael Collins"]},
            {"id": "g_e_7", "question": "What is the tallest land mammal in the world?", "correctAnswer": "Giraffe", "incorrectAnswers": ["African Elephant", "Hippopotamus", "Rhinoceros"]},
            {"id": "g_e_8", "question": "In which country can you visit the ancient Pyramids of Giza?", "correctAnswer": "Egypt", "incorrectAnswers": ["Greece", "Mexico", "Peru"]},
            {"id": "g_e_9", "question": "What is the freezing point of water in degrees Celsius?", "correctAnswer": "0°C", "incorrectAnswers": ["32°C", "-10°C", "100°C"]},
            {"id": "g_e_10", "question": "Which sport awards the prestigious FIFA World Cup trophy?", "correctAnswer": "Football (Soccer)", "incorrectAnswers": ["Cricket", "Basketball", "Rugby"]},
            {"id": "g_e_11", "question": "What natural disaster is measured using the Richter scale?", "correctAnswer": "Earthquake", "incorrectAnswers": ["Tornado", "Tsunami", "Volcanic Eruption"]},
            {"id": "g_e_12", "question": "Which primary organ pumps blood throughout the human body?", "correctAnswer": "Heart", "incorrectAnswers": ["Lungs", "Brain", "Liver"]},
            {"id": "g_e_13", "question": "What currency is officially used in Japan?", "correctAnswer": "Yen", "incorrectAnswers": ["Won", "Yuan", "Baht"]},
            {"id": "g_e_14", "question": "What is the largest rainforest in the world?", "correctAnswer": "Amazon Rainforest", "incorrectAnswers": ["Congo Basin", "Daintree Rainforest", "Sundarbans"]},
            {"id": "g_e_15", "question": "Which European country is famous for tulip fields and windmills?", "correctAnswer": "Netherlands", "incorrectAnswers": ["Belgium", "Switzerland", "Denmark"]},
            {"id": "g_e_16", "question": "How many days are in a standard leap year?", "correctAnswer": "366 days", "incorrectAnswers": ["365 days", "364 days", "367 days"]},
            {"id": "g_e_17", "question": "Which gas do plants absorb from the air during photosynthesis?", "correctAnswer": "Carbon Dioxide (CO2)", "incorrectAnswers": ["Oxygen", "Nitrogen", "Methane"]},
            {"id": "g_e_18", "question": "What is the national animal of Australia?", "correctAnswer": "Red Kangaroo", "incorrectAnswers": ["Koala", "Emu", "Platypus"]},
            {"id": "g_e_19", "question": "Which ancient civilization built Machu Picchu high in the Andes mountains?", "correctAnswer": "Inca", "incorrectAnswers": ["Maya", "Aztec", "Olmec"]},
            {"id": "g_e_20", "question": "What color flag is internationally recognized as a symbol of surrender?", "correctAnswer": "White", "incorrectAnswers": ["Red", "Yellow", "Blue"]}
        ],
        "medium": [
            {"id": "g_m_1", "question": "What is the longest river in the world by consensus?", "correctAnswer": "Nile River", "incorrectAnswers": ["Amazon River", "Yangtze River", "Mississippi River"]},
            {"id": "g_m_2", "question": "In what year did the historic Apollo 11 moon landing take place?", "correctAnswer": "1969", "incorrectAnswers": ["1965", "1972", "1959"]},
            {"id": "g_m_3", "question": "Which country has the greatest number of natural lakes in the world?", "correctAnswer": "Canada", "incorrectAnswers": ["Russia", "United States", "Finland"]},
            {"id": "g_m_4", "question": "Who developed the general theory of relativity in physics?", "correctAnswer": "Albert Einstein", "incorrectAnswers": ["Isaac Newton", "Niels Bohr", "Galileo Galilei"]},
            {"id": "g_m_5", "question": "What is the capital city of Australia?", "correctAnswer": "Canberra", "incorrectAnswers": ["Sydney", "Melbourne", "Brisbane"]},
            {"id": "g_m_6", "question": "Which element has the chemical symbol 'Au' on the periodic table?", "correctAnswer": "Gold", "incorrectAnswers": ["Silver", "Copper", "Aluminum"]},
            {"id": "g_m_7", "question": "What strait separates southern Spain from northern Morocco in Africa?", "correctAnswer": "Strait of Gibraltar", "incorrectAnswers": ["Bosporus Strait", "Strait of Hormuz", "Strait of Malacca"]},
            {"id": "g_m_8", "question": "In which city did the ancient Olympic Games originate?", "correctAnswer": "Olympia, Greece", "incorrectAnswers": ["Athens, Greece", "Rome, Italy", "Sparta, Greece"]},
            {"id": "g_m_9", "question": "What is the hardest known natural mineral on Mohs scale?", "correctAnswer": "Diamond", "incorrectAnswers": ["Corundum", "Topaz", "Quartz"]},
            {"id": "g_m_10", "question": "Which famous scientist formulated the laws of planetary motion?", "correctAnswer": "Johannes Kepler", "incorrectAnswers": ["Nicolaus Copernicus", "Tycho Brahe", "Edmond Halley"]},
            {"id": "g_m_11", "question": "What is the largest desert in the world (including polar areas)?", "correctAnswer": "Antarctic Desert", "incorrectAnswers": ["Sahara Desert", "Arabian Desert", "Gobi Desert"]},
            {"id": "g_m_12", "question": "Which human blood type is considered the universal red cell donor?", "correctAnswer": "O Negative (O-)", "incorrectAnswers": ["AB Positive (AB+)", "A Positive (A+)", "B Negative (B-)"]},
            {"id": "g_m_13", "question": "In what year did the Titanic sink on its maiden voyage?", "correctAnswer": "1912", "incorrectAnswers": ["1905", "1918", "1923"]},
            {"id": "g_m_14", "question": "What is the official currency of the United Kingdom?", "correctAnswer": "Pound Sterling", "incorrectAnswers": ["Euro", "Crown", "Franc"]},
            {"id": "g_m_15", "question": "What layer of Earth's atmosphere contains the vital ozone layer?", "correctAnswer": "Stratosphere", "incorrectAnswers": ["Troposphere", "Mesosphere", "Thermosphere"]},
            {"id": "g_m_16", "question": "Who was the first woman to win a Nobel Prize and the only person to win in two scientific fields?", "correctAnswer": "Marie Curie", "incorrectAnswers": ["Rosalind Franklin", "Lise Meitner", "Ada Lovelace"]},
            {"id": "g_m_17", "question": "Which African nation was formerly known as Abyssinia?", "correctAnswer": "Ethiopia", "incorrectAnswers": ["Eritrea", "Sudan", "Somalia"]},
            {"id": "g_m_18", "question": "What is the speed of light in a vacuum (approximate km/s)?", "correctAnswer": "300,000 km/s", "incorrectAnswers": ["150,000 km/s", "500,000 km/s", "1,000,000 km/s"]},
            {"id": "g_m_19", "question": "Which country spans 11 time zones across Europe and Asia?", "correctAnswer": "Russia", "incorrectAnswers": ["Canada", "China", "United States"]},
            {"id": "g_m_20", "question": "What is the highest mountain peak above sea level on Earth?", "correctAnswer": "Mount Everest", "incorrectAnswers": ["K2", "Kangchenjunga", "Lhotse"]}
        ],
        "hard": [
            {"id": "g_h_1", "question": "Which treaty in 1648 ended the Thirty Years' War and established modern national sovereignty?", "correctAnswer": "Peace of Westphalia", "incorrectAnswers": ["Treaty of Utrecht", "Treaty of Versailles", "Treaty of Tordesillas"]},
            {"id": "g_h_2", "question": "What is the deepest point in the world's oceans, located in the Mariana Trench?", "correctAnswer": "Challenger Deep", "incorrectAnswers": ["Sirena Deep", "Milwaukee Deep", "Java Trench"]},
            {"id": "g_h_3", "question": "Which ancient wonder of the world was located in the city of Alexandria in Egypt?", "correctAnswer": "Lighthouse of Alexandria", "incorrectAnswers": ["Colossus of Rhodes", "Temple of Artemis", "Mausoleum at Halicarnassus"]},
            {"id": "g_h_4", "question": "What is the chemical element with the highest melting point of all metals (3,422°C)?", "correctAnswer": "Tungsten (Wolfram)", "incorrectAnswers": ["Titanium", "Platinum", "Osmium"]},
            {"id": "g_h_5", "question": "Which African country is completely surrounded by South Africa as an enclave?", "correctAnswer": "Lesotho", "incorrectAnswers": ["Eswatini", "Botswana", "Namibia"]},
            {"id": "g_h_6", "question": "In what year did the Byzantine capital Constantinople fall to Ottoman Sultan Mehmed II?", "correctAnswer": "1453", "incorrectAnswers": ["1492", "1204", "1517"]},
            {"id": "g_h_7", "question": "What is the densest naturally occurring chemical element on Earth?", "correctAnswer": "Osmium", "incorrectAnswers": ["Lead", "Iridium", "Uranium"]},
            {"id": "g_h_8", "question": "Which archipelago in the South Atlantic was the site of a 1982 conflict between the UK and Argentina?", "correctAnswer": "Falkland Islands (Islas Malvinas)", "incorrectAnswers": ["Galapagos Islands", "South Georgia", "Azores"]},
            {"id": "g_h_9", "question": "Who was the British mathematician who cracked the German Enigma cipher at Bletchley Park?", "correctAnswer": "Alan Turing", "incorrectAnswers": ["John von Neumann", "Claude Shannon", "Charles Babbage"]},
            {"id": "g_h_10", "question": "What is the driest non-polar desert on Earth, located along the Pacific coast in South America?", "correctAnswer": "Atacama Desert", "incorrectAnswers": ["Kalahari Desert", "Namib Desert", "Sonoran Desert"]},
            {"id": "g_h_11", "question": "Which Roman Emperor officially moved the imperial capital from Rome to Byzantium in 330 AD?", "correctAnswer": "Constantine the Great", "incorrectAnswers": ["Julius Caesar", "Augustus", "Marcus Aurelius"]},
            {"id": "g_h_12", "question": "What is the rarest naturally occurring element in Earth's crust, with less than 30 grams existing at any time?", "correctAnswer": "Astatine", "incorrectAnswers": ["Francium", "Promethium", "Polonium"]},
            {"id": "g_h_13", "question": "Which strait connects the Black Sea directly to the Sea of Marmara?", "correctAnswer": "Bosporus Strait", "incorrectAnswers": ["Dardanelles Strait", "Kerch Strait", "Gibraltar Strait"]},
            {"id": "g_h_14", "question": "Who wrote the ancient political treatise 'Arthashastra' in classical India?", "correctAnswer": "Chanakya (Kautilya)", "incorrectAnswers": ["Ashoka", "Aryabhata", "Kalidasa"]},
            {"id": "g_h_15", "question": "What is the SI unit of magnetic flux density?", "correctAnswer": "Tesla", "incorrectAnswers": ["Weber", "Henry", "Gauss"]},
            {"id": "g_h_16", "question": "Which nation was the first in modern history to grant all women the right to vote in parliamentary elections (1893)?", "correctAnswer": "New Zealand", "incorrectAnswers": ["Australia", "Finland", "United Kingdom"]},
            {"id": "g_h_17", "question": "What volcanic eruption in Indonesia in 1815 caused 1816 to be known as 'The Year Without a Summer'?", "correctAnswer": "Mount Tambora", "incorrectAnswers": ["Krakatoa", "Mount Pinatubo", "Mount Toba"]},
            {"id": "g_h_18", "question": "Which fundamental subatomic particle mediates the electromagnetic force?", "correctAnswer": "Photon", "incorrectAnswers": ["Gluon", "W Boson", "Graviton"]},
            {"id": "g_h_19", "question": "What ancient trade network linked China and the Mediterranean across Central Asia for centuries?", "correctAnswer": "The Silk Road", "incorrectAnswers": ["The Amber Road", "The Incense Route", "The Royal Road"]},
            {"id": "g_h_20", "question": "Which body of water is the lowest land-based elevation on Earth (-430 meters below sea level)?", "correctAnswer": "Dead Sea", "incorrectAnswers": ["Caspian Sea", "Lake Baikal", "Lake Assal"]}
        ]
    }
}

# ============================================================================
# HELPER STORAGE FUNCTIONS
# ============================================================================
def _load_json(path: Path, default):
    with LOCK:
        if not path.exists():
            return default
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[QuestionProvider] Error reading {path.name}: {e}")
            return default

def _save_json(path: Path, data):
    with LOCK:
        temp_path = path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(path)
        except Exception as e:
            print(f"[QuestionProvider] Error writing {path.name}: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

def normalize_question(item: dict):
    """
    Normalizes trivia questions from The Trivia API v2 or local cache.
    Fixes the common 'incorrect_answers' vs 'incorrectAnswers' discrepancy,
    and checks question text whether it is a string or an object {text: '...'}.
    """
    if not isinstance(item, dict):
        return None

    q_id = str(item.get("id") or item.get("question_id") or random.randint(100000, 999999))

    # Question text normalization
    raw_question = item.get("question")
    if isinstance(raw_question, dict):
        q_text = raw_question.get("text", "")
    elif isinstance(raw_question, str):
        q_text = raw_question
    else:
        q_text = ""
    q_text = q_text.strip()

    # Correct answer normalization
    correct = item.get("correctAnswer") or item.get("correct_answer") or ""
    correct = str(correct).strip()

    # Incorrect answers normalization (fixes previous incorrect_answers cache error)
    incorrect = item.get("incorrectAnswers")
    if incorrect is None:
        incorrect = item.get("incorrect_answers")

    if isinstance(incorrect, str):
        incorrect = [incorrect]
    elif not isinstance(incorrect, list):
        incorrect = []

    clean_incorrect = []
    for inc in incorrect:
        val = str(inc).strip()
        if val and val != correct and val not in clean_incorrect:
            clean_incorrect.append(val)

    # Must have question text, a valid correct answer, and at least 3 distinct distractors
    if not q_text or not correct or len(clean_incorrect) < 3:
        return None

    return {
        "id": q_id,
        "question": q_text,
        "correctAnswer": correct,
        "incorrectAnswers": clean_incorrect[:3],
        "category": str(item.get("category", "")),
        "difficulty": str(item.get("difficulty", "")).lower()
    }

# ============================================================================
# API FETCHING
# ============================================================================
def fetch_from_api(category_key: str, difficulty_key: str, limit: int = 30):
    """
    Fetches raw questions from The Trivia API v2 with category and difficulty filters.
    """
    cat_info = CATEGORIES.get(category_key, {})
    api_categories = cat_info.get("api_categories", [])

    params = {
        "difficulties": difficulty_key,
        "limit": str(limit),
    }
    if api_categories:
        params["categories"] = ",".join(api_categories)

    query_str = urllib.parse.urlencode(params)
    url = f"{API_URL}?{query_str}"

    headers = {
        "User-Agent": "QuizArena-Interactive/2.0 (Windows; Educational Installation)"
    }
    if API_KEY:
        headers["X-API-KEY"] = API_KEY

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=6.0) as resp:
            if resp.status == 200:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
                if isinstance(data, list):
                    normalized = []
                    for item in data:
                        norm = normalize_question(item)
                        if norm:
                            normalized.append(norm)
                    return normalized
    except urllib.error.HTTPError as e:
        print(f"[QuestionProvider] The Trivia API HTTP error: {e.code} ({e.reason})")
    except urllib.error.URLError as e:
        print(f"[QuestionProvider] The Trivia API network error: {e.reason}")
    except Exception as e:
        print(f"[QuestionProvider] Unexpected API error: {e}")

    return []

# ============================================================================
# CORE QUESTION SELECTION & BALANCING
# ============================================================================
def get_cached_pool(category: str, difficulty: str):
    """Returns the question pool from local cache + built-in fallbacks."""
    cache = _load_json(CACHE_FILE, {})
    cache_key = f"{category}:{difficulty}"
    cached_list = cache.get(cache_key, [])

    normalized_cache = []
    seen_ids = set()
    for item in cached_list:
        norm = normalize_question(item)
        if norm and norm["id"] not in seen_ids:
            seen_ids.add(norm["id"])
            normalized_cache.append(norm)

    # Merge built-in fallbacks
    fallbacks = FALLBACK_QUESTIONS.get(category, {}).get(difficulty, [])
    for item in fallbacks:
        norm = normalize_question(item)
        if norm and norm["id"] not in seen_ids:
            seen_ids.add(norm["id"])
            normalized_cache.append(norm)

    return normalized_cache

def update_cache_pool(category: str, difficulty: str, fresh_items: list):
    """Merges newly fetched items into the persistent cache file."""
    if not fresh_items:
        return
    with LOCK:
        cache = _load_json(CACHE_FILE, {})
        cache_key = f"{category}:{difficulty}"
        existing = cache.get(cache_key, [])
        existing_ids = {x.get("id") for x in existing if isinstance(x, dict)}

        for item in fresh_items:
            norm = normalize_question(item)
            if norm and norm["id"] not in existing_ids:
                existing_ids.add(norm["id"])
                existing.append(norm)

        cache[cache_key] = existing
        _save_json(CACHE_FILE, cache)

def choose_questions(category: str, difficulty: str):
    """
    Selects 20 questions for the interactive quiz:
    1. Fetches from The Trivia API, updates local cache.
    2. Limits repeats to at most MAX_REPEATS (5) from previous matching session.
    3. Perfectly balances correct answers: 5 A's, 5 B's, 5 C's, 5 D's.
    """
    category = category.lower().strip()
    difficulty = difficulty.lower().strip()

    if category not in CATEGORIES:
        category = "tech"
    if difficulty not in DIFFICULTIES:
        difficulty = "medium"

    cache_key = f"{category}:{difficulty}"

    # Step 1: Try fetching fresh questions from API
    fresh_fetched = fetch_from_api(category, difficulty, limit=35)
    if fresh_fetched:
        update_cache_pool(category, difficulty, fresh_fetched)

    # Step 2: Load complete pool (cache + fallbacks)
    pool = get_cached_pool(category, difficulty)

    # Step 3: Check history to limit immediate repeats
    history_data = _load_json(HISTORY_FILE, {})
    last_history_ids = set(history_data.get(cache_key, []))

    non_repeat_candidates = [q for q in pool if q["id"] not in last_history_ids]
    repeat_candidates = [q for q in pool if q["id"] in last_history_ids]

    random.shuffle(non_repeat_candidates)
    random.shuffle(repeat_candidates)

    selected_pool = []

    # If we have enough non-repeats, use them directly
    if len(non_repeat_candidates) >= QUESTION_COUNT:
        selected_pool = non_repeat_candidates[:QUESTION_COUNT]
    else:
        # Take all available non-repeats
        selected_pool.extend(non_repeat_candidates)
        needed = QUESTION_COUNT - len(selected_pool)

        # Allow at most MAX_REPEATS from previous session
        repeats_allowed = min(needed, MAX_REPEATS, len(repeat_candidates))
        selected_pool.extend(repeat_candidates[:repeats_allowed])

        # If pool is still short of 20, fill remainder from any candidate in pool
        if len(selected_pool) < QUESTION_COUNT:
            remaining_repeats = [q for q in pool if q not in selected_pool]
            random.shuffle(remaining_repeats)
            selected_pool.extend(remaining_repeats[: QUESTION_COUNT - len(selected_pool)])

    # Ultimate safety guarantee: exactly QUESTION_COUNT items
    while len(selected_pool) < QUESTION_COUNT:
        filler = random.choice(pool)
        # clone with unique ID so client never conflicts
        clone = dict(filler)
        clone["id"] = f"{filler['id']}_{random.randint(100, 999)}"
        selected_pool.append(clone)

    selected_pool = selected_pool[:QUESTION_COUNT]
    random.shuffle(selected_pool)

    # Step 4: Record newly selected IDs in history for this category & difficulty
    new_history_ids = [q["id"] for q in selected_pool]
    history_data[cache_key] = new_history_ids
    _save_json(HISTORY_FILE, history_data)

    # Step 5: Answer distribution balancing
    # For 20 questions, exactly 5 have answer at index 0 (A), 5 at 1 (B), 5 at 2 (C), 5 at 3 (D)
    balanced_slots = [0] * 5 + [1] * 5 + [2] * 5 + [3] * 5
    random.shuffle(balanced_slots)

    final_questions = []
    for i, q in enumerate(selected_pool):
        correct_target_index = balanced_slots[i]
        incorrect_options = list(q["incorrectAnswers"])
        random.shuffle(incorrect_options)

        options = [None, None, None, None]
        options[correct_target_index] = q["correctAnswer"]

        distractor_idx = 0
        for slot in range(4):
            if slot != correct_target_index:
                options[slot] = incorrect_options[distractor_idx]
                distractor_idx += 1

        final_questions.append({
            "id": q["id"],
            "question": q["question"],
            "options": options,
            "correct": correct_target_index
        })

    return final_questions

if __name__ == "__main__":
    print("Testing question_provider...")
    qs = choose_questions("tech", "easy")
    print(f"Generated {len(qs)} questions.")
    counts = [0, 0, 0, 0]
    for q in qs:
        counts[q["correct"]] += 1
    print(f"Answer distribution (A, B, C, D): {counts} -> Exactly 5 each!")

