import re
import spacy
from typing import Dict, List, Set, Optional
from io import BytesIO
from collections import defaultdict

# PDF extraction with fallbacks
try:
    import pdfplumber  # Better than PyPDF2
    PDF_LIBRARY = 'pdfplumber'
except ImportError:
    import PyPDF2
    PDF_LIBRARY = 'PyPDF2'

class ImprovedResumeParser:
    def __init__(self):
        # Load spaCy with NER
        self.nlp = spacy.load("en_core_web_sm")
        
        # Comprehensive skill ontology with synonyms
        self.SKILL_KEYWORDS = {
            'frontend': {
                'react': ['react', 'reactjs', 'react.js', 'react js'],
                'vue': ['vue', 'vuejs', 'vue.js'],
                'angular': ['angular', 'angularjs'],
                'javascript': ['javascript', 'js', 'ecmascript'],
                'typescript': ['typescript', 'ts'],
                'html': ['html', 'html5'],
                'css': ['css', 'css3', 'scss', 'sass', 'less'],
                'tailwind': ['tailwind', 'tailwindcss'],
                'nextjs': ['next.js', 'nextjs', 'next'],
                'svelte': ['svelte', 'sveltekit'],
                'webpack': ['webpack', 'vite', 'rollup'],
            },
            'backend': {
                'python': ['python', 'python3'],
                'django': ['django'],
                'flask': ['flask'],
                'fastapi': ['fastapi', 'fast api'],
                'nodejs': ['node.js', 'nodejs', 'node'],
                'express': ['express', 'expressjs'],
                'java': ['java', 'java ee', 'jakarta ee'],
                'spring': ['spring', 'spring boot', 'springboot'],
                'golang': ['go', 'golang'],
                'rust': ['rust'],
                'ruby': ['ruby', 'ruby on rails', 'rails'],
                'php': ['php', 'laravel', 'symfony'],
                'csharp': ['c#', 'csharp', '.net', 'dotnet', 'asp.net'],
            },
            'mobile': {
                'react_native': ['react native', 'react-native'],
                'flutter': ['flutter', 'dart'],
                'swift': ['swift', 'swiftui'],
                'kotlin': ['kotlin'],
                'android': ['android', 'android studio'],
                'ios': ['ios', 'xcode'],
            },
            'ml_ai': {
                'tensorflow': ['tensorflow', 'tf', 'keras'],
                'pytorch': ['pytorch', 'torch'],
                'sklearn': ['scikit-learn', 'sklearn', 'scikit learn'],
                'ml': ['machine learning', 'ml'],
                'dl': ['deep learning', 'dl', 'neural networks'],
                'nlp': ['nlp', 'natural language processing'],
                'cv': ['computer vision', 'cv', 'opencv'],
                'transformers': ['transformers', 'bert', 'gpt', 'llm'],
            },
            'data': {
                'sql': ['sql', 'mysql', 'mssql', 't-sql'],
                'postgresql': ['postgresql', 'postgres'],
                'mongodb': ['mongodb', 'mongo'],
                'redis': ['redis'],
                'elasticsearch': ['elasticsearch', 'elastic'],
                'spark': ['apache spark', 'spark', 'pyspark'],
                'hadoop': ['hadoop', 'mapreduce'],
                'pandas': ['pandas'],
                'numpy': ['numpy'],
            },
            'devops': {
                'docker': ['docker', 'dockerfile', 'containerization'],
                'kubernetes': ['kubernetes', 'k8s'],
                'aws': ['aws', 'amazon web services', 'ec2', 's3', 'lambda'],
                'azure': ['azure', 'microsoft azure'],
                'gcp': ['gcp', 'google cloud', 'google cloud platform'],
                'cicd': ['ci/cd', 'jenkins', 'github actions', 'gitlab ci'],
                'terraform': ['terraform', 'iac'],
                'ansible': ['ansible'],
            },
            'design': {
                'figma': ['figma'],
                'sketch': ['sketch'],
                'adobe': ['photoshop', 'illustrator', 'adobe xd'],
                'uiux': ['ui/ux', 'ui', 'ux', 'user experience', 'user interface'],
            }
        }
        
        # Build reverse lookup: synonym -> canonical name
        self.skill_synonyms = {}
        for category, skills_dict in self.SKILL_KEYWORDS.items():
            for canonical, synonyms in skills_dict.items():
                for synonym in synonyms:
                    self.skill_synonyms[synonym.lower()] = {
                        'canonical': canonical,
                        'category': category
                    }
        
        # Role patterns
        self.ROLE_PATTERNS = {
            'frontend': ['frontend', 'front-end', 'front end', 'ui developer', 'react developer', 'vue developer', 'web developer'],
            'backend': ['backend', 'back-end', 'back end', 'server', 'api developer', 'backend engineer'],
            'fullstack': ['fullstack', 'full-stack', 'full stack', 'full-stack developer'],
            'ml_engineer': ['machine learning', 'ml engineer', 'ai engineer', 'data scientist', 'ml developer'],
            'mobile': ['mobile developer', 'ios developer', 'android developer', 'app developer'],
            'designer': ['designer', 'ui/ux', 'product designer', 'graphic designer', 'ux designer'],
            'devops': ['devops', 'sre', 'site reliability', 'platform engineer', 'infrastructure engineer'],
            'data_engineer': ['data engineer', 'data engineering', 'etl developer'],
        }
        
        # Email regex
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        
        # Phone regex (basic, supports various formats)
        self.phone_pattern = re.compile(r'[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]')
        
        # GitHub/LinkedIn patterns
        self.github_pattern = re.compile(r'github\.com/[\w-]+', re.IGNORECASE)
        self.linkedin_pattern = re.compile(r'linkedin\.com/in/[\w-]+', re.IGNORECASE)
        
        # Hackathon-related keywords for extraction
        self.HACKATHON_KEYWORDS = [
            'hackathon', 'hack-a-thon', 'hacktoberfest', 'hackfest',
            'coding competition', 'coding challenge', 'datathon',
            'mlh', 'major league hacking', 'devpost',
            'google solution challenge', 'eth india', 'eth global',
            'smart india hackathon', 'sih'
        ]
        
        # Placement keywords (winner, runner-up, etc.)
        self.PLACEMENT_KEYWORDS = {
            'first': ['winner', 'won', '1st place', 'first place', 'first prize', 'champions', 'gold'],
            'second': ['runner up', 'runner-up', '2nd place', 'second place', 'second prize', 'silver'],
            'third': ['3rd place', 'third place', 'third prize', 'bronze'],
            'finalist': ['finalist', 'top 10', 'top 5', 'top 3', 'shortlisted', 'selected'],
            'participant': ['participated', 'attendee', 'competed']
        }
        
        # Prize amount patterns
        self.prize_pattern = re.compile(r'[\$₹€£]\s*[\d,]+(?:\.\d{2})?(?:k|K)?|\b(?:prize|cash|won)\s+(?:of\s+)?[\$₹€£]\s*[\d,]+', re.IGNORECASE)
    
    def extract_experience_section(self, text: str) -> str:
        """
        Extract just the experience/work section from resume
        This helps focus company extraction on relevant sections
        """
        lines = text.split('\n')
        experience_section = []
        in_experience = False
        
        for i, line in enumerate(lines):
            line_lower = line.lower().strip()
            
            # Detect start of experience section
            if any(keyword in line_lower for keyword in [
                'experience', 'work history', 'employment', 'professional experience',
                'work experience', 'career'
            ]) and not any(skip in line_lower for skip in ['years', 'total', 'summary']):
                in_experience = True
                continue
            
            # Detect end of experience section (new section starts)
            if in_experience and line and not line.startswith(' ') and not line.startswith('\t'):
                if any(keyword in line_lower for keyword in [
                    'education', 'skills', 'projects', 'certifications', 
                    'achievements', 'awards', 'publications', 'languages'
                ]):
                    break
            
            if in_experience:
                experience_section.append(line)
        
        return '\n'.join(experience_section) if experience_section else text
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF with better library"""
        try:
            if PDF_LIBRARY == 'pdfplumber':
                import pdfplumber
                text = ""
                with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                return text
            else:
                # Fallback to PyPDF2
                pdf_reader = PyPDF2.PdfReader(BytesIO(pdf_bytes))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text
        except Exception as e:
            print(f"Error extracting PDF: {e}")
            return ""
    
    def extract_contact_info(self, text: str) -> Dict[str, Optional[str]]:
        """Extract email, phone, GitHub, LinkedIn"""
        email_match = self.email_pattern.search(text)
        phone_match = self.phone_pattern.search(text)
        github_match = self.github_pattern.search(text)
        linkedin_match = self.linkedin_pattern.search(text)
        
        return {
            'email': email_match.group(0) if email_match else None,
            'phone': phone_match.group(0) if phone_match else None,
            'github': f"https://{github_match.group(0)}" if github_match else None,
            'linkedin': f"https://{linkedin_match.group(0)}" if linkedin_match else None,
        }
    
    def extract_name(self, text: str) -> Optional[str]:
        """Extract person's name using NER"""
        doc = self.nlp(text[:500])  # Check first 500 chars
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                return ent.text
        return None
    
    def extract_skills(self, text: str) -> Dict[str, List[str]]:
        """Extract skills with synonym handling"""
        text_lower = text.lower()
        found_skills = defaultdict(set)
        
        # Search for all skill synonyms
        for synonym, skill_info in self.skill_synonyms.items():
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(synonym) + r'\b'
            if re.search(pattern, text_lower):
                canonical = skill_info['canonical']
                category = skill_info['category']
                found_skills[category].add(canonical)
        
        # Convert sets to lists
        return {k: sorted(list(v)) for k, v in found_skills.items()}
    
    def extract_roles(self, text: str) -> List[str]:
        """Extract roles with better matching"""
        text_lower = text.lower()
        roles = set()
        
        for role, patterns in self.ROLE_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    roles.add(role)
                    break
        
        return sorted(list(roles))
    
    def extract_experience_years(self, text: str) -> int:
        """Extract years of experience with multiple patterns"""
        patterns = [
            r'(\d+)\+?\s*years?\s+(?:of\s+)?experience',
            r'experience[:\s]+(\d+)\+?\s*years?',
            r'(\d+)\+?\s*yrs?\s+(?:of\s+)?experience',
        ]
        
        years = []
        for pattern in patterns:
            matches = re.finditer(pattern, text.lower())
            for match in matches:
                years.append(int(match.group(1)))
        
        return max(years) if years else 0
    
    def extract_education(self, text: str) -> List[Dict[str, str]]:
        """Extract education with degree type and field"""
        degrees = []
        text_lower = text.lower()
        
        degree_patterns = [
            (r'bachelor[\'s]*\s+(?:of\s+)?(?:science|arts|engineering|technology)?\s*(?:in\s+)?([a-z\s]+)?', 'Bachelor'),
            (r'master[\'s]*\s+(?:of\s+)?(?:science|arts|engineering|technology)?\s*(?:in\s+)?([a-z\s]+)?', 'Master'),
            (r'(?:phd|ph\.d\.|doctorate)\s*(?:in\s+)?([a-z\s]+)?', 'PhD'),
            (r'b\.?tech|b\.?e\.\s*(?:in\s+)?([a-z\s]+)?', 'B.Tech'),
            (r'm\.?tech|m\.?e\.\s*(?:in\s+)?([a-z\s]+)?', 'M.Tech'),
        ]
        
        for pattern, degree_type in degree_patterns:
            matches = re.finditer(pattern, text_lower)
            for match in matches:
                field = match.group(1).strip() if match.lastindex and match.group(1) else 'Unknown'
                degrees.append({
                    'degree': degree_type,
                    'field': field[:50]  # Limit field length
                })
        
        return degrees
    
    def extract_work_experience(self, text: str) -> List[Dict]:
        """Extract company names using NER with filtering"""
        doc = self.nlp(text)
        
        # Common false positives to filter out
        BLACKLIST = set([
            # Programming languages
            'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'ruby',
            'go', 'rust', 'php', 'swift', 'kotlin', 'scala', 'r',
            # Technologies/Frameworks
            'react', 'angular', 'vue', 'node', 'django', 'flask', 'spring',
            'express', 'fastapi', 'tensorflow', 'pytorch', 'kubernetes',
            'docker', 'aws', 'azure', 'mongodb', 'postgresql', 'redis',
            'elasticsearch', 'kafka', 'spark', 'hadoop', 'jenkins',
            # Skills/Tools
            'git', 'github', 'gitlab', 'jira', 'figma', 'photoshop',
            'linux', 'windows', 'mac', 'ios', 'android',
            # Common resume words
            'experience', 'education', 'skills', 'projects', 'achievements',
            'responsibilities', 'summary', 'objective', 'references'
        ])
        
        # Known tech companies (real companies to keep)
        KNOWN_COMPANIES = set([
            'google', 'microsoft', 'amazon', 'facebook', 'meta', 'apple',
            'netflix', 'tesla', 'twitter', 'uber', 'airbnb', 'spotify',
            'linkedin', 'salesforce', 'oracle', 'ibm', 'intel', 'nvidia',
            'adobe', 'atlassian', 'shopify', 'stripe', 'paypal', 'square',
            'dropbox', 'zoom', 'slack', 'github', 'gitlab', 'cloudflare',
            'tcs', 'infosys', 'wipro', 'cognizant', 'accenture', 'deloitte',
            'pwc', 'ey', 'kpmg', 'flipkart', 'paytm', 'swiggy', 'zomato',
            'ola', 'byju', 'oyo'
        ])
        
        companies = []
        seen = set()
        
        # Strategy 1: Look for org entities that are likely companies
        for ent in doc.ents:
            if ent.label_ == "ORG":
                text_lower = ent.text.lower().strip()
                
                # Skip if it's in blacklist
                if text_lower in BLACKLIST:
                    continue
                
                # Skip if it's a single word tech term
                if ' ' not in ent.text and text_lower in BLACKLIST:
                    continue
                
                # Skip if it's too short and not a known company
                if len(text_lower) <= 3 and text_lower not in KNOWN_COMPANIES:
                    continue
                
                # Skip if it's all uppercase abbreviation (might be skill like "ML", "AI", "CI/CD")
                if ent.text.isupper() and len(ent.text) <= 5:
                    continue
                
                # Keep if it's a known company or looks like a real company
                if (text_lower in KNOWN_COMPANIES or 
                    ' ' in ent.text or  # Multi-word (likely company)
                    any(word in text_lower for word in ['inc', 'ltd', 'corp', 'llc', 'pvt', 'technologies', 'solutions', 'systems', 'labs'])):
                    
                    if text_lower not in seen:
                        companies.append(ent.text)
                        seen.add(text_lower)
        
        # Strategy 2: Look for common patterns like "at Company" or "Company (dates)"
        company_patterns = [
            r'(?:at|@)\s+([A-Z][A-Za-z0-9\s&\-\.]+?)(?:\s*[\(,\n]|$)',  # "at Google" or "@ Microsoft"
            r'([A-Z][A-Za-z0-9\s&\-\.]+?)\s*[\(]\s*\d{4}',  # "Google (2020"
            r'(?:worked|working|employed)\s+(?:at|for|with)\s+([A-Z][A-Za-z0-9\s&\-\.]+?)(?:\s*[\(,\n]|$)',
        ]
        
        for pattern in company_patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                company_name = match.group(1).strip()
                company_lower = company_name.lower()
                
                # Apply same filters
                if (company_lower not in BLACKLIST and 
                    company_lower not in seen and
                    len(company_name) > 3):
                    
                    # Additional check: should contain at least one capital letter
                    if any(c.isupper() for c in company_name):
                        companies.append(company_name)
                        seen.add(company_lower)
        
        # Return top 5 unique companies
        return [{'company': comp} for comp in companies[:5]]
    
    def extract_hackathon_wins(self, text: str) -> Dict:
        """
        Extract hackathon wins, placements, and achievements
        Returns structured data about hackathon participations
        """
        text_lower = text.lower()
        lines = text.split('\n')
        
        hackathon_achievements = []
        total_hackathons = 0
        wins_count = {'first': 0, 'second': 0, 'third': 0, 'finalist': 0, 'participant': 0}
        total_prize_money = []
        
        # Find sections that likely contain hackathons
        achievement_sections = []
        in_achievement_section = False
        current_section = []
        
        for line in lines:
            line_lower = line.lower().strip()
            
            # Detect achievement/hackathon sections
            if any(keyword in line_lower for keyword in ['achievement', 'hackathon', 'competition', 'award', 'honor']):
                if 'education' not in line_lower and 'experience' not in line_lower:
                    in_achievement_section = True
                    if current_section:
                        achievement_sections.append('\n'.join(current_section))
                    current_section = [line]
                    continue
            
            if in_achievement_section:
                if line.strip() and not line.startswith(' '):
                    # New section might have started
                    if any(keyword in line_lower for keyword in ['experience', 'education', 'skill', 'project']) and 'hackathon' not in line_lower:
                        in_achievement_section = False
                        achievement_sections.append('\n'.join(current_section))
                        current_section = []
                        continue
                current_section.append(line)
        
        if current_section:
            achievement_sections.append('\n'.join(current_section))
        
        # If no clear sections found, search entire text
        if not achievement_sections:
            achievement_sections = [text]
        
        # Parse each achievement section
        for section in achievement_sections:
            section_lower = section.lower()
            
            # Find hackathon mentions
            for hackathon_keyword in self.HACKATHON_KEYWORDS:
                if hackathon_keyword in section_lower:
                    # Extract context around the keyword (nearby lines)
                    context_lines = []
                    section_lines = section.split('\n')
                    
                    for i, line in enumerate(section_lines):
                        if hackathon_keyword in line.lower():
                            # Get this line and next few lines for context
                            context_start = max(0, i - 1)
                            context_end = min(len(section_lines), i + 3)
                            context = ' '.join(section_lines[context_start:context_end])
                            context_lines.append(context)
                    
                    for context in context_lines:
                        context_lower = context.lower()
                        
                        # Determine placement
                        placement = 'participant'
                        for place, keywords in self.PLACEMENT_KEYWORDS.items():
                            if any(keyword in context_lower for keyword in keywords):
                                placement = place
                                break
                        
                        # Extract hackathon name (simplified - get capitalized words near keyword)
                        hackathon_name_match = re.search(
                            r'([A-Z][a-zA-Z0-9\s&\-]+(?:hackathon|Hackathon|challenge|Challenge|competition|Competition)[a-zA-Z0-9\s\-]*)',
                            context
                        )
                        hackathon_name = hackathon_name_match.group(1).strip() if hackathon_name_match else "Unnamed Hackathon"
                        
                        # Extract year
                        year_match = re.search(r'\b(20\d{2})\b', context)
                        year = int(year_match.group(1)) if year_match else None
                        
                        # Extract prize money
                        prize_match = self.prize_pattern.search(context)
                        prize = prize_match.group(0) if prize_match else None
                        if prize:
                            # Try to extract numeric value
                            prize_value = re.search(r'[\d,]+(?:\.\d{2})?', prize.replace(',', ''))
                            if prize_value:
                                total_prize_money.append(prize_value.group(0))
                        
                        # Extract tech stack used
                        tech_used = []
                        for synonym, skill_info in self.skill_synonyms.items():
                            if synonym in context_lower:
                                tech_used.append(skill_info['canonical'])
                        
                        # Create achievement entry
                        achievement = {
                            'hackathon_name': hackathon_name[:100],  # Limit length
                            'placement': placement,
                            'year': year,
                            'prize': prize,
                            'tech_stack': list(set(tech_used))[:5],  # Top 5 unique
                            'context': context[:200]  # Store snippet for verification
                        }
                        
                        hackathon_achievements.append(achievement)
                        wins_count[placement] += 1
                        total_hackathons += 1
        
        # Remove duplicates (same hackathon mentioned multiple times)
        unique_achievements = []
        seen_names = set()
        for achievement in hackathon_achievements:
            name_key = achievement['hackathon_name'].lower()
            if name_key not in seen_names:
                seen_names.add(name_key)
                unique_achievements.append(achievement)
        
        # Calculate hackathon score (weighted by placement)
        hackathon_score = (
            wins_count['first'] * 10 +
            wins_count['second'] * 7 +
            wins_count['third'] * 5 +
            wins_count['finalist'] * 3 +
            wins_count['participant'] * 1
        )
        
        return {
            'total_hackathons': len(unique_achievements),
            'achievements': unique_achievements,
            'wins_breakdown': wins_count,
            'hackathon_score': hackathon_score,
            'total_prizes': total_prize_money,
            'has_hackathon_experience': len(unique_achievements) > 0
        }
    
    def parse_resume(self, pdf_bytes: bytes = None, text: str = None) -> Dict:
        """Main parsing function - comprehensive extraction"""
        if pdf_bytes:
            text = self.extract_text_from_pdf(pdf_bytes)
        
        if not text or len(text.strip()) < 50:
            return {"error": "No meaningful text to parse", "raw_text": text[:200]}
        
        # Extract all components
        contact_info = self.extract_contact_info(text)
        name = self.extract_name(text)
        skills = self.extract_skills(text)
        roles = self.extract_roles(text)
        experience_years = self.extract_experience_years(text)
        education = self.extract_education(text)
        work_experience = self.extract_work_experience(text)
        hackathon_data = self.extract_hackathon_wins(text)
        
        # Flatten skills for easy access
        all_skills_flat = []
        for category_skills in skills.values():
            all_skills_flat.extend(category_skills)
        
        return {
            "name": name,
            "contact": contact_info,
            "skills_by_category": skills,
            "all_skills": sorted(list(set(all_skills_flat))),
            "roles": roles,
            "experience_years": experience_years,
            "education": education,
            "work_experience": work_experience,
            "hackathons": hackathon_data,  # NEW: Hackathon achievements
            "raw_text_preview": text[:500],
            "total_text_length": len(text),
            "parsing_library": PDF_LIBRARY
        }


# Usage example
if __name__ == "__main__":
    parser = ImprovedResumeParser()
    
    # Test with sample text
    sample_text = """
    John Doe
    john.doe@email.com | github.com/johndoe | +1-234-567-8900
    
    Senior Full-Stack Developer
    
    Experienced software engineer with 5 years of experience building scalable web applications.
    
    Technical Skills:
    • Frontend: React.js, TypeScript, Next.js, TailwindCSS, HTML5, CSS3
    • Backend: Python, FastAPI, Node.js, Express, PostgreSQL, MongoDB
    • DevOps: Docker, Kubernetes, AWS (EC2, S3, Lambda), CI/CD
    • Machine Learning: PyTorch, TensorFlow, Scikit-learn, NLP
    
    Experience:
    Software Engineer at Google (2020-Present)
    - Built ML-powered recommendation systems
    
    Junior Developer at Microsoft (2018-2020)
    - Developed REST APIs using FastAPI
    
    Education:
    Bachelor's in Computer Science from Stanford University
    Master of Science in Artificial Intelligence
    
    Achievements & Hackathons:
    • Winner - Smart India Hackathon 2023 - Built an AI-powered healthcare platform using React and TensorFlow. Prize: $10,000
    • Runner-up - ETH India 2022 - Developed a blockchain-based supply chain solution with Solidity and Node.js
    • Finalist - Google Solution Challenge 2021 - Created a disaster management app with Flutter and Firebase
    • Participated in MLH Hackathon 2020 - Built a chatbot using Python and NLP
    • 1st Place - College Tech Fest Hackathon 2019 - IoT project with Raspberry Pi. Won ₹50,000
    
    Projects:
    - Open source contributor to React ecosystem
    - Built 10+ full-stack applications
    
    Interests: Hackathons, Open Source, AI Research
    """
    
    result = parser.parse_resume(text=sample_text)
    
    print("=== PARSED RESUME ===")
    print(f"Name: {result.get('name')}")
    print(f"Email: {result['contact'].get('email')}")
    print(f"GitHub: {result['contact'].get('github')}")
    print(f"\nSkills by Category:")
    for category, skills in result['skills_by_category'].items():
        print(f"  {category}: {', '.join(skills)}")
    print(f"\nAll Skills: {', '.join(result['all_skills'])}")
    print(f"Roles: {', '.join(result['roles'])}")
    print(f"Experience: {result['experience_years']} years")
    print(f"\nEducation:")
    for edu in result['education']:
        print(f"  {edu['degree']} in {edu['field']}")
    print(f"\nCompanies: {[w['company'] for w in result['work_experience']]}")
    
    # NEW: Display hackathon data
    print(f"\n=== HACKATHON ACHIEVEMENTS ===")
    hackathon_data = result['hackathons']
    print(f"Total Hackathons: {hackathon_data['total_hackathons']}")
    print(f"Hackathon Score: {hackathon_data['hackathon_score']}/100")
    print(f"Wins Breakdown: {hackathon_data['wins_breakdown']}")
    print(f"\nDetailed Achievements:")
    for i, achievement in enumerate(hackathon_data['achievements'], 1):
        print(f"\n  {i}. {achievement['hackathon_name']}")
        print(f"     Placement: {achievement['placement'].upper()}")
        if achievement['year']:
            print(f"     Year: {achievement['year']}")
        if achievement['prize']:
            print(f"     Prize: {achievement['prize']}")
        if achievement['tech_stack']:
            print(f"     Tech Used: {', '.join(achievement['tech_stack'])}")