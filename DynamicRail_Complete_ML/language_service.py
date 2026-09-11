# 23-language UI set = English + India's 22 Scheduled Languages.
import re

LANGUAGES = {
    "en": "English", "hi": "Hindi", "as": "Assamese", "bn": "Bengali", "brx": "Bodo", "doi": "Dogri",
    "gu": "Gujarati", "kn": "Kannada", "ks": "Kashmiri", "kok": "Konkani", "mai": "Maithili", "ml": "Malayalam",
    "mni": "Manipuri", "mr": "Marathi", "ne": "Nepali", "or": "Odia", "pa": "Punjabi", "sa": "Sanskrit",
    "sat": "Santali", "sd": "Sindhi", "ta": "Tamil", "te": "Telugu", "ur": "Urdu"
}

LABELS = {
    "en": {"eta": "Estimated arrival", "delay": "Current delay", "reason": "Delay reason", "risk": "Propagation risk"},
    "hi": {"eta": "अनुमानित आगमन", "delay": "वर्तमान देरी", "reason": "देरी का कारण", "risk": "देरी फैलने का जोखिम"},
    "bn": {"eta": "আনুমানিক আগমন", "delay": "বর্তমান বিলম্ব", "reason": "বিলম্বের কারণ", "risk": "বিলম্ব ছড়ানোর ঝুঁকি"},
    "mr": {"eta": "अंदाजे आगमन", "delay": "सध्याचा विलंब", "reason": "विलंबाचे कारण", "risk": "विलंब पसरण्याचा धोका"},
    "gu": {"eta": "અંદાજિત આગમન", "delay": "વર્તમાન વિલંબ", "reason": "વિલંબનું કારણ", "risk": "વિલંબ ફેલાવાનું જોખમ"},
    "ta": {"eta": "மதிப்பிடப்பட்ட வருகை", "delay": "தற்போதைய தாமதம்", "reason": "தாமத காரணம்", "risk": "தாமதம் பரவும் அபாயம்"},
    "te": {"eta": "అంచనా రాక సమయం", "delay": "ప్రస్తుత ఆలస్యం", "reason": "ఆలస్యానికి కారణం", "risk": "ఆలస్యం వ్యాపించే ప్రమాదం"},
    "kn": {"eta": "ಅಂದಾಜು ಆಗಮನ", "delay": "ಪ್ರಸ್ತುತ ವಿಳಂಬ", "reason": "ವಿಳಂಬದ ಕಾರಣ", "risk": "ವಿಳಂಬ ಹರಡುವ ಅಪಾಯ"},
    "ml": {"eta": "കണക്കാക്കിയ വരവ്", "delay": "നിലവിലെ വൈകിപ്പ്", "reason": "വൈകിപ്പിന്റെ കാരണം", "risk": "വൈകിപ്പ് പകരാനുള്ള അപകടസാധ്യത"},
    "pa": {"eta": "ਅਨੁਮਾਨਿਤ ਪਹੁੰਚ", "delay": "ਮੌਜੂਦਾ ਦੇਰੀ", "reason": "ਦੇਰੀ ਦਾ ਕਾਰਨ", "risk": "ਦੇਰੀ ਫੈਲਣ ਦਾ ਖਤਰਾ"},
    "or": {"eta": "ଆନୁମାନିକ ପହଞ୍ଚ", "delay": "ବର୍ତ୍ତମାନ ବିଳମ୍ବ", "reason": "ବିଳମ୍ବର କାରଣ", "risk": "ବିଳମ୍ବ ପ୍ରସାରଣ ଝୁମ୍କି"},
    "as": {"eta": "আনুমানিক আগমন", "delay": "বৰ্তমান বিলম্ব", "reason": "বিলম্বৰ কাৰণ", "risk": "বিলম্ব বিয়পোৱাৰ আশংকা"},
    "ur": {"eta": "متوقع آمد", "delay": "موجودہ تاخیر", "reason": "تاخیر کی وجہ", "risk": "تاخیر پھیلنے کا خطرہ"},
}

CHAT_TEMPLATES = {
    "en": {
        "reason": "Delay reason: {reason}. Expected additional delay is +{add_mins} minutes.",
        "delay": "Current running delay is {cur_mins} minutes. Predicted additional delay: +{add_mins} minutes.",
        "eta": "Estimated arrival time is {eta}. Dynamic forecast interval: {lower} to {upper}.",
        "where": "Your train is in transit with running status: {status}. Live telemetry is actively monitored.",
        "weather": "Current weather along the route includes regional visibility conditions and speed restrictions integrated into the ETA model.",
        "route": "Your train is progressing along its scheduled route. Signals and section occupancy are actively monitored.",
        "platform": "The expected arrival platform will be updated upon section clearance at the approaching station.",
        "propagation": "Potential propagation risk to downstream trains: {risk} (probability {prob:.0%}).",
        "fallback": "I can provide real-time updates for ETA, current running delay, delay reasons, weather conditions, and network impact."
    },
    "hi": {
        "reason": "देरी का कारण: {reason}। अनुमानित अतिरिक्त देरी +{add_mins} मिनट है।",
        "delay": "वर्तमान रनिंग देरी {cur_mins} मिनट है। अनुमानित अतिरिक्त देरी: +{add_mins} मिनट।",
        "eta": "अनुमानित आगमन समय: {eta} है (पूर्वानुमान अंतराल: {lower} से {upper})।",
        "where": "आपकी ट्रेन वर्तमान में मार्ग पर चल रही है (स्थिति: {status})। लाइव टेलीमेट्री की निगरानी जारी है।",
        "weather": "मार्ग में दृश्यता और मौसम संबंधी स्थितियों को एआई आगमन समय में शामिल किया गया है।",
        "route": "ट्रेन अपने निर्धारित मार्ग पर आगे बढ़ रही है। सिग्नलों और ट्रैक स्थिति की लगातार निगरानी की जा रही है।",
        "platform": "अपेक्षित प्लेटफॉर्म की जानकारी अगले स्टेशन पर सेक्शन क्लीयरेंस के समय अपडेट की जाएगी।",
        "propagation": "अन्य ट्रेनों पर देरी फैलने का जोखिम: {risk} (संभावना {prob:.0%})।",
        "fallback": "मैं ट्रेन के आगमन समय (ETA), वर्तमान देरी, देरी के कारण, मौसम और रूट की जानकारी दे सकता हूँ।"
    },
    "bn": {
        "reason": "বিলম্বের কারণ: {reason}। প্রত্যাশিত অতিরিক্ত বিলম্ব +{add_mins} মিনিট।",
        "delay": "বর্তমান চলমান বিলম্ব {cur_mins} মিনিট। পূর্বাভাসিত অতিরিক্ত বিলম্ব: +{add_mins} মিনিট।",
        "eta": "আনুমানিক পৌঁছানোর সময়: {eta} (পূর্বাভাস ব্যবধান: {lower} থেকে {upper})।",
        "where": "আপনার ট্রেন বর্তমানে যাত্রাপথে চলছে (অবস্থা: {status})। লাইভ টেলিমেট্রি সক্রিয়ভাবে পর্যবেক্ষণ করা হচ্ছে।",
        "weather": "যাত্রাপথের আবহাওয়া ও কুয়াশার প্রভাব এআই পূর্বাভাস মডেলে সংযুক্ত রয়েছে।",
        "route": "ট্রেনটি নির্ধারিত রুটে অগ্রসর হচ্ছে এবং সেকশন ট্র্যাকিং সক্রিয় রয়েছে।",
        "platform": "পরবর্তী স্টেশনে পৌঁছানোর পূর্বে প্ল্যাটফর্ম নম্বর নিশ্চিত করা হবে।",
        "propagation": "অন্য ট্রেনে বিলম্ব ছড়ানোর ঝুঁকি: {risk} (সম্ভাবনা {prob:.0%})।",
        "fallback": "আমি ট্রেনের আগমন সময় (ETA), বর্তমান বিলম্ব, বিলম্বের কারণ এবং আবহাওয়ার তথ্য প্রদান করতে পারি।"
    },
    "te": {
        "reason": "ఆలస్యానికి కారణం: {reason}. అంచనా వేసిన అదనపు ఆలస్యం +{add_mins} నిమిషాలు.",
        "delay": "ప్రస్తుత రన్నింగ్ ఆలస్యం {cur_mins} నిమిషాలు. అంచనా వేసిన అదనపు ఆలస్యం: +{add_mins} నిమిషాలు.",
        "eta": "అంచనా రాక సమయం: {eta} (అంచనా పరిధి: {lower} నుండి {upper}).",
        "where": "మీ రైలు ప్రస్తుతం మార్గంలో నడుస్తోంది (స్థితి: {status}). లైవ్ టెలిమెట్రీ పర్యవేక్షించబడుతోంది.",
        "weather": "మార్గంలో వాతావరణ పరిస్థితులు మరియు వేగ పరిమితులు ఏఐ మోడల్‌లో చేర్చబడ్డాయి.",
        "route": "రైలు తన నిర్దేశిత మార్గంలో ప్రయాణిస్తోంది. సిగ్నలింగ్ ట్రాకింగ్ సక్రియంగా ఉంది.",
        "platform": "రాబోయే స్టేషన్‌లో ప్లాట్‌ఫారమ్ వివరాలు త్వరలో నవీకరించబడతాయి.",
        "propagation": "ఇతర రైళ్లకు ఆలస్యం వ్యాపించే ప్రమాదం: {risk} (సంభావ్యత {prob:.0%}).",
        "fallback": "నేను రైలు రాక సమయం (ETA), ప్రస్తుత ఆలస్యం, ఆలస్య కారణాలు మరియు వాతావరణ సమాచారాన్ని అందించగలను."
    },
    "mr": {
        "reason": "विलंबाचे कारण: {reason}. अपेक्षित अतिरिक्त विलंब +{add_mins} मिनिटे आहे.",
        "delay": "सध्याचा धावण्याचा विलंब {cur_mins} मिनिटे आहे. अंदाजित अतिरिक्त विलंब: +{add_mins} मिनिटे.",
        "eta": "अंदाजे आगमन वेळ: {eta} आहे (अंदाज कालावधी: {lower} ते {upper}).",
        "where": "तुमची ट्रेन सध्या मार्गावर धावत आहे (स्थिती: {status}). थेट टेलीमेट्रीचे निरीक्षण केले जात आहे.",
        "weather": "मार्गावरील हवामान व धुक्याची परिस्थिती AI मॉडेलमध्ये समाविष्ट केली आहे.",
        "route": "ट्रेन नियोजित मार्गावर पुढे जात असून सिग्नल स्थितीवर लक्ष ठेवले जात आहे.",
        "platform": "पुढील स्थानकावर पोहोचण्यापूर्वी प्लॅटफॉर्म क्रमांक अपडेट केला जाईल.",
        "propagation": "इतर गाड्यांवर विलंब पसरण्याचा धोका: {risk} (शक्यता {prob:.0%}).",
        "fallback": "मी आगमन वेळ (ETA), चालू विलंब, विलंबाची कारणे आणि हवामानाची माहिती देऊ शकतो."
    },
    "ta": {
        "reason": "தாமத காரணம்: {reason}. எதிர்பார்க்கப்படும் கூடுதல் தாமதம் +{add_mins} நிமிடங்கள்.",
        "delay": "தற்போதைய தாமதம் {cur_mins} நிமிடங்கள். கணிக்கப்பட்ட கூடுதல் தாமதம்: +{add_mins} நிமிடங்கள்.",
        "eta": "மதிப்பிடப்பட்ட வருகை நேரம்: {eta} (கணிப்பு இடைவெளி: {lower} முதல் {upper}).",
        "where": "உங்கள் ரயில் தற்போது பயணத்தில் உள்ளது (நிலை: {status}). நேரடி டெலிமெட்ரி கண்காணிக்கப்படுகிறது.",
        "weather": "வழித்தட வானிலை மற்றும் பார்வைத் திறன் காரணிகள் AI கணிப்பில் சேர்க்கப்பட்டுள்ளன.",
        "route": "ரயில் திட்டமிட்ட பாதையில் சென்று கொண்டிருக்கிறது. சிக்னல் கண்காணிப்பு செயலில் உள்ளது.",
        "platform": "அடுத்த நிலையத்தில் நடைமேடை எண் விரைவில் புதுப்பிக்கப்படும்.",
        "propagation": "மற்ற ரயில்களுக்கு தாமதம் பரவும் அபாயம்: {risk} (சாத்தியம் {prob:.0%}).",
        "fallback": "வருகை நேரம் (ETA), தற்போதைய தாமதம், தாமதக் காரணங்கள் மற்றும் வானிலை விவரங்களை நான் வழங்க முடியும்."
    },
    "gu": {
        "reason": "વિલંબનું કારણ: {reason}. અપેક્ષિત વધારાનો વિલંબ +{add_mins} મિનિટ છે.",
        "delay": "વર્તમાન દોડવાનો વિલંબ {cur_mins} મિનિટ છે. અંદાજિત વધારાનો વિલંબ: +{add_mins} મિનિટ.",
        "eta": "અંદાજિત આગમન સમય: {eta} છે (આગાહી અંતરાલ: {lower} થી {upper}).",
        "where": "તમારી ટ્રેન હાલમાં માર્ગ પર દોડી રહી છે (સ્થિતિ: {status}). લાઇવ ટેલિમેટ્રીનું નિરીક્ષણ ચાલુ છે.",
        "weather": "માર્ગ પરનું હવામાન અને વિઝિબિલિટી ડેટા AI પ્રિડિક્શનમાં સામેલ છે.",
        "route": "ટ્રેન નિયત રૂટ પર આગળ વધી રહી છે અને સિગ્નલિંગ ટ્રેકિંગ ચાલુ છે.",
        "platform": "આગામી સ્ટેશને પ્લેટફોર્મ નંબર ટૂંક સમયમાં ઉપલબ્ધ થશે.",
        "propagation": "અન્ય ટ્રેનો પર વિલંબ ફેલાવાનું જોખમ: {risk} (સંભાવના {prob:.0%}).",
        "fallback": "હું ટ્રેન આગમન સમય (ETA), વર્તમાન વિલંબ, વિલંબના કારણો અને હવામાન વિગતો આપી શકું છું."
    },
    "ur": {
        "reason": "تاخیر کی وجہ: {reason}۔ متوقع اضافی تاخیر +{add_mins} منٹ ہے۔",
        "delay": "موجودہ رننگ تاخیر {cur_mins} منٹ ہے۔ متوقع اضافی تاخیر: +{add_mins} منٹ۔",
        "eta": "متوقع آمد کا وقت: {eta} ہے (پیشین گوئی وقفہ: {lower} تا {upper})۔",
        "where": "آپ کی ٹرین فی الحال راستے میں ہے (حیثیت: {status})۔ لائیو ٹیلی میٹری کی مسلسل نگرانی کی جا رہی ہے۔",
        "weather": "راستے کے موسم اور حد نگاہ کے اثرات کو AI آمد کے وقت میں شامل کیا گیا ہے۔",
        "route": "ٹرین اپنے مقررہ راستے پر گامزن ہے اور ٹریک کی مسلسل نگرانی جاری ہے۔",
        "platform": "اگلے اسٹیشن پر پلیٹ فارم نمبر جلد اپ ڈیٹ کیا جائے گا۔",
        "propagation": "دوسری ٹرینوں پر تاخیر پھیلنے کا خطرہ: {risk} (امکان {prob:.0%})۔",
        "fallback": "میں متوقع آمد کا وقت (ETA)، موجودہ تاخیر، تاخیر کی وجوہات اور موسم کی معلومات فراہم کر سکتا ہوں۔"
    },
    "kn": {
        "reason": "ವಿಳಂಬದ ಕಾರಣ: {reason}. ನಿರೀಕ್ಷಿತ ಹೆಚ್ಚುವರಿ ವಿಳಂಬ +{add_mins} ನಿಮಿಷಗಳು.",
        "delay": "ಪ್ರಸ್ತುತ ಚಾಲನೆಯಲ್ಲಿರುವ ವಿಳಂಬ {cur_mins} ನಿಮಿಷಗಳು. ಮುನ್ಸೂಚಿತ ಹೆಚ್ಚುವರಿ ವಿಳಂಬ: +{add_mins} ನಿಮಿಷಗಳು.",
        "eta": "ಅಂದಾಜು ಆಗಮನ ಸಮಯ: {eta} (ಮುನ್ಸೂಚನೆ ಶ್ರೇಣಿ: {lower} ರಿಂದ {upper}).",
        "where": "ನಿಮ್ಮ ರೈಲು ಪ್ರಸ್ತುತ ಮಾರ್ಗದಲ್ಲಿದೆ (ಸ್ಥಿತಿ: {status}). ಲೈವ್ ಟೆಲಿಮೆಟ್ರಿಯನ್ನು ನಿರಂತರವಾಗಿ ಮೇಲ್ವಿಚಾರಣೆ ಮಾಡಲಾಗುತ್ತಿದೆ.",
        "weather": "ಮಾರ್ಗದ ಹವಾಮಾನ ಮತ್ತು ಮಂಜಿನ ಪರಿಸ್ಥಿತಿಗಳನ್ನು AI ಮುನ್ಸೂಚನೆಯಲ್ಲಿ ಪರಿಗಣಿಸಲಾಗಿದೆ.",
        "route": "ರೈಲು ನಿಗದಿತ ಮಾರ್ಗದಲ್ಲಿ ಮುಂದುವರಿಯುತ್ತಿದ್ದು, ಸಿಗ್ನಲಿಂಗ್ ಟ್ರ್ಯಾಕಿಂಗ್ ಸಕ್ರಿಯವಾಗಿದೆ.",
        "platform": "ಮುಂದಿನ ನಿಲ್ದಾಣದ ಪ್ಲಾಟ್‌ಫಾರ್ಮ್ ವಿವರಗಳನ್ನು ಶೀಘ್ರದಲ್ಲೇ ನವೀಕರಿಸಲಾಗುವುದು.",
        "propagation": "ಇತರ ರೈಲುಗಳಿಗೆ ವಿಳಂಬ ಹರಡುವ ಅಪಾಯ: {risk} (ಸಾಧ್ಯತೆ {prob:.0%}).",
        "fallback": "ನಾನು ರೈಲು ಆಗಮನ ಸಮಯ (ETA), ಪ್ರಸ್ತುತ ವಿಳಂಬ, ವಿಳಂಬದ ಕಾರಣಗಳು ಮತ್ತು ಹವಾಮಾನ ಮಾಹಿತಿಯನ್ನು ನೀಡಬಲ್ಲೆ."
    },
    "or": {
        "reason": "ବିଳମ୍ବର କାରଣ: {reason}। ପ୍ରତ୍ୟାଶିତ ଅତିରିକ୍ତ ବିଳମ୍ବ +{add_mins} ମିନିଟ୍।",
        "delay": "ବର୍ତ୍ତମାନର ଚାଲୁଥିବା ବିଳମ୍ବ {cur_mins} ମିନିଟ୍। ଅନୁମାନିତ ଅତିରିକ୍ତ ବିଳମ୍ବ: +{add_mins} ମିନିଟ୍।",
        "eta": "ଆନୁମାନିକ ପହଞ୍ଚିବା ସମୟ: {eta} (ପୂର୍ବାନୁମାନ ବ୍ୟବଧାନ: {lower} ରୁ {upper})।",
        "where": "ଆପଣଙ୍କ ଟ୍ରେନ୍ ବର୍ତ୍ତମାନ ଯାତ୍ରାରେ ଅଛି (ସ୍ଥିତି: {status})। ଲାଇଭ୍ ଟେଲିମେଟ୍ରି ନିରୀକ୍ଷଣ କରାଯାଉଛି।",
        "weather": "ରୁଟ୍‌ର ପାଣିପାଗ ଏବଂ କୁହୁଡ଼ି ସ୍ଥିତି AI ପୂର୍ବାନୁମାନରେ ଅନ୍ତର୍ଭୁକ୍ତ।",
        "route": "ଟ୍ରେନ୍ ନିର୍ଦ୍ଧାରିତ ମାର୍ଗରେ ଚାଲୁଅଛି ଏବଂ ସିଗ୍‌ନାଲ୍ ନିରୀକ୍ଷଣ ଜାରି ରହିଛି।",
        "platform": "ପରବର୍ତ୍ତୀ ଷ୍ଟେସନରେ ପ୍ଲାଟଫର୍ମ ନମ୍ବର ଶୀଘ୍ର ଉପଲବ୍ଧ ହେବ।",
        "propagation": "ଅନ୍ୟ ଟ୍ରେନକୁ ବିଳମ୍ବ ବ୍ୟାପିବାର ଆଶଙ୍କା: {risk} (ସମ୍ଭାବନା {prob:.0%})।",
        "fallback": "ମୁଁ ଆଗମନ ସମୟ (ETA), ବର୍ତ୍ତମାନର ବିଳମ୍ବ, କାରଣ ଏବଂ ପାଣିପାଗ ବିବରଣୀ ପ୍ରଦାନ କରିପାରିବି।"
    },
    "ml": {
        "reason": "വൈകലിന്റെ കാരണം: {reason}. പ്രതീക്ഷിക്കുന്ന അധിക വൈകൽ +{add_mins} മിനിറ്റ്.",
        "delay": "നിലവിലെ റണ്ണിംഗ് വൈകൽ {cur_mins} മിനിറ്റാണ്. പ്രവചിച്ച അധിക വൈകൽ: +{add_mins} മിനിറ്റ്.",
        "eta": "കണക്കാക്കിയ വരവ് സമയം: {eta} ആണ് (പ്രവചന പരിധി: {lower} മുതൽ {upper}).",
        "where": "നിങ്ങളുടെ ട്രെയിൻ നിലവിൽ യാത്രയിലാണ് (നില: {status}). തത്സമയ ടെലിമെട്രി നിരീക്ഷിക്കുന്നു.",
        "weather": "യാത്രാമാർഗ്ഗത്തിലെ കാലാവസ്ഥയും മൂടൽമഞ്ഞും AI പ്രവചനത്തിൽ ഉൾപ്പെടുത്തിയിട്ടുണ്ട്.",
        "route": "ട്രെയിൻ നിശ്ചിത റൂട്ടിലൂടെ മുന്നോട്ട് പോകുന്നു. സിഗ്നൽ ട്രാക്കിംഗ് സജീവമാണ്.",
        "platform": "അടുത്ത സ്റ്റേഷനിലെ പ്ലാറ്റ്‌ഫോം വിവരങ്ങൾ ഉടൻ ലഭ്യമാകും.",
        "propagation": "മറ്റ് ട്രെയിനുകളിലേക്ക് വൈകൽ പകരാനുള്ള സാധ്യത: {risk} (സാധ്യത {prob:.0%}).",
        "fallback": "വരവ് സമയം (ETA), നിലവിലെ വൈകൽ, കാരണങ്ങൾ, കാലാവസ്ഥാ വിവരങ്ങൾ എന്നിവ എനിക്ക് നൽകാനാകും."
    },
    "pa": {
        "reason": "ਦੇਰੀ ਦਾ ਕਾਰਨ: {reason}। ਅਨੁਮਾਨਿਤ ਵਾਧੂ ਦੇਰੀ +{add_mins} ਮਿੰਟ ਹੈ।",
        "delay": "ਮੌਜੂਦਾ ਚੱਲ ਰਹੀ ਦੇਰੀ {cur_mins} ਮਿੰਟ ਹੈ। ਅਨੁਮਾਨਿਤ ਵਾਧੂ ਦੇਰੀ: +{add_mins} ਮਿੰਟ।",
        "eta": "ਅਨੁਮਾਨਿਤ ਪਹੁੰਚ ਸਮਾਂ: {eta} ਹੈ (ਅੰਦਾਜ਼ਾ ਸੀਮਾ: {lower} ਤੋਂ {upper})।",
        "where": "ਤੁਹਾਡੀ ਟ੍ਰੇਨ ਇਸ ਵੇਲੇ ਰਸਤੇ ਵਿੱਚ ਹੈ (ਸਥਿਤੀ: {status})। ਲਾਈਵ ਟੈਲੀਮੈਟਰੀ ਦੀ ਨਿਗਰਾਨੀ ਕੀਤੀ ਜਾ ਰਹੀ ਹੈ।",
        "weather": "ਰਸਤੇ ਵਿੱਚ ਮੌਸਮ ਅਤੇ ਧੁੰਦ ਦੀ ਸਥਿਤੀ AI ਭਵਿੱਖਬਾਣੀ ਵਿੱਚ ਸ਼ਾਮਲ ਹੈ।",
        "route": "ਟ੍ਰੇਨ ਨਿਰਧਾਰਿਤ ਰੂਟ 'ਤੇ ਅੱਗੇ ਵੱਧ ਰਹੀ ਹੈ ਅਤੇ ਸਿਗਨਲ ਨਿਗਰਾਨੀ ਸਰਗਰਮ ਹੈ।",
        "platform": "ਅਗਲੇ ਸਟੇਸ਼ਨ 'ਤੇ ਪਲੇਟਫਾਰਮ ਨੰਬਰ ਜਲਦੀ ਹੀ ਅੱਪਡੇਟ ਕੀਤਾ ਜਾਵੇਗਾ।",
        "propagation": "ਦੂਜੀਆਂ ਟ੍ਰੇਨਾਂ 'ਤੇ ਦੇਰੀ ਫੈਲਣ ਦਾ ਖਤਰਾ: {risk} (ਸੰਭਾਵਨਾ {prob:.0%})।",
        "fallback": "ਮੈਂ ਟ੍ਰੇਨ ਦੇ ਪਹੁੰਚਣ ਦੇ ਸਮੇਂ (ETA), ਮੌਜੂਦਾ ਦੇਰੀ, ਕਾਰਨਾਂ ਅਤੇ ਮੌਸਮ ਜਾਣਕਾਰੀ ਵਿੱਚ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ।"
    },
    "as": {
        "reason": "বিলম্বৰ কাৰণ: {reason}। প্ৰত্যাশিত অতিৰিক্ত বিলম্ব +{add_mins} মিনিট।",
        "delay": "বৰ্তমানৰ চলন্ত বিলম্ব {cur_mins} মিনিট। অনুমাণিক অতিৰিক্ত বিলম্ব: +{add_mins} মিনিট।",
        "eta": "অনুমাণিক আগমনৰ সময়: {eta} (পূৰ্বাভাস পৰিসৰ: {lower} ৰ পৰা {upper})।",
        "where": "আপোনাৰ ৰেলখন বৰ্তমান যাত্ৰাপথত আছে (স্থিতি: {status})। লাইভ টেলিমেট্ৰি নিৰীক্ষণ কৰা হৈছে।",
        "weather": "যাত্ৰাপথৰ বতৰ আৰু কুঁৱলীৰ প্ৰভাৱ AI পূৰ্বাভাসত অন্তৰ্ভুক্ত কৰা হৈছে।",
        "route": "ৰেলখন নিৰ্ধাৰিত পথত অগ্ৰসৰ হৈছে আৰু ট্ৰেক নিৰীক্ষণ সক্ৰিয় আছে।",
        "platform": "পৰৱৰ্তী ষ্টেচনত প্লেটফৰ্ম নম্বৰ সোনকালে আপডেট কৰা হ'ব।",
        "propagation": "অন্য ৰেললৈ বিলম্ব বিয়পোৱাৰ আশংকা: {risk} (সম্ভাৱনা {prob:.0%})।",
        "fallback": "মই আগমনৰ সময় (ETA), চলিত বিলম্ব, কাৰণ আৰু বতৰৰ তথ্য প্ৰদান কৰিব পাৰোঁ।"
    }
}

# Fill remaining official languages with contextual Hindi-heritage templates
for code in LANGUAGES.keys():
    if code not in CHAT_TEMPLATES:
        CHAT_TEMPLATES[code] = CHAT_TEMPLATES["hi"].copy()


REASON_CONTRIBUTORS = {
    "high current delay": {
        "en": "high current delay",
        "hi": "वर्तमान में अत्यधिक देरी",
        "bn": "বর্তমান উচ্চ বিলম্ব",
        "te": "ప్రస్తుత అధిక ఆలస్యం",
        "mr": "सध्याचा जास्त विलंब",
        "ta": "தற்போதைய அதிக தாமதம்",
        "gu": "વર્તમાન ઊંચો વિલંબ",
        "ur": "موجودہ زیادہ تاخیر",
        "kn": "ಪ್ರಸ್ತುತ ಹೆಚ್ಚಿನ ವಿಳಂಬ",
        "or": "ବର୍ତ୍ତମାନର ଅଧିକ ବିଳମ୍ବ",
        "ml": "നിലവിലെ ഉയർന്ന വൈകൽ",
        "pa": "ਮੌਜੂਦਾ ਜ਼ਿਆਦਾ ਦੇਰੀ",
        "as": "বৰ্তমান অধিক বিলম্ব"
    },
    "reduced current speed": {
        "en": "reduced current speed",
        "hi": "ट्रेन की कम गति",
        "bn": "হ্রাসপ্রাপ্ত ট্রেনের গতি",
        "te": "తగ్గిన ప్రస్తుత వేగం",
        "mr": "कमी झालेला वेग",
        "ta": "குறைக்கப்பட்ட தற்போதைய வேகம்",
        "gu": "ઘટાડેલી વર્તમાન ઝડપ",
        "ur": "موجودہ رفتار میں کمی",
        "kn": "ಕಡಿಮೆಯಾದ ಪ್ರಸ್ತುತ ವೇಗ",
        "or": "ହ୍ରାସ ପାଇଥିବା ଗତି",
        "ml": "കുറഞ്ഞ വേഗത",
        "pa": "ਘਟੀ ਹੋਈ ਗਤੀ",
        "as": "হ্ৰাস পোৱা গতি"
    },
    "high section congestion": {
        "en": "high section congestion",
        "hi": "सेक्शन में भारी ट्रैफिक जमाव",
        "bn": "সেকশনে উচ্চ যানজট",
        "te": "సెక్షన్‌లో అధిక రద్దీ",
        "mr": "सेक्शनमध्ये जास्त ट्रॅफिक",
        "ta": "பிரிவில் அதிக நெரிசல்",
        "gu": "સેક્શનમાં ભારે ટ્રાફિક ભીડ",
        "ur": "سیکشن میں زیادہ ٹریفک رش",
        "kn": "ವಿಭಾಗದಲ್ಲಿ ಹೆಚ್ಚಿನ ದಟ್ಟಣೆ",
        "or": "ସେକ୍ସନରେ ଅଧିକ ଭିଡ଼",
        "ml": "സെക്ഷനിലെ ഉയർന്ന തിരക്ക്",
        "pa": "ਸੈਕਸ਼ਨ ਵਿੱਚ ਭਾਰੀ ਭੀੜ",
        "as": "ছেকচনত অধিক যানজঁট"
    },
    "multiple trains ahead": {
        "en": "multiple trains ahead",
        "hi": "आगे कई ट्रेनों का परिचालन",
        "bn": "সামনে একাধিক ট্রেন চলাচল",
        "te": "ముందు పలు రైళ్ల రాకపోకలు",
        "mr": "पुढे अनेक गाड्यांचे संचलन",
        "ta": "முன்னால் பல ரயில்கள் இயக்கம்",
        "gu": "આગળ ઘણી ટ્રેનોનું સંચાલન",
        "ur": "آگے متعدد ٹرینوں کی موجودگی",
        "kn": "ಮುಂದೆ ಹಲವಾರು ರೈಲುಗಳ ಸಂಚಾರ",
        "or": "ଆଗରେ ଏକାଧିକ ଟ୍ରେନ୍",
        "ml": "മുന്നിൽ ഒന്നിലധികം ട്രെയിനുകൾ",
        "pa": "ਅੱਗੇ ਕਈ ਟ੍ਰੇਨਾਂ",
        "as": "আগত একাধিক ৰেল"
    },
    "speed restriction": {
        "en": "speed restriction",
        "hi": "गति सीमा प्रतिबंध",
        "bn": "গতি সীমাবদ্ধতা",
        "te": "వేగ పరిమితి",
        "mr": "वेग मर्यादा",
        "ta": "வேகக் கட்டுப்பாடு",
        "gu": "ઝડપ મર્યાદા",
        "ur": "رفتار پر پابندی",
        "kn": "ವೇಗ ಮಿತಿ",
        "or": "ଗତି ନିୟନ୍ତ୍ରଣ",
        "ml": "വേഗപരിധി",
        "pa": "ਗਤੀ ਪਾਬੰਦੀ",
        "as": "গতি বাধা"
    },
    "active track maintenance": {
        "en": "active track maintenance",
        "hi": "ट्रैक मरम्मत कार्य",
        "bn": "ট্র্যাক মেরামতের কাজ",
        "te": "ట్రాక్ నిర్వహణ పనులు",
        "mr": "ट्रॅक दुरुस्तीचे काम",
        "ta": "தண்டவாள பராமரிப்புப் பணி",
        "gu": "ટ્રેક સમારકામ",
        "ur": "ٹریک کی فعال مرمت",
        "kn": "ಟ್ರ್ಯಾಕ್ ನಿರ್ವಹಣೆ ಕಾರ್ಯ",
        "or": "ଟ୍ରାକ୍ ମରାମତି କାର୍ଯ୍ୟ",
        "ml": "ട്രാക്ക് അറ്റകുറ്റപ്പണി",
        "pa": "ਟ੍ਰੈਕ ਮੁਰੰਮਤ ਕਾਰਜ",
        "as": "ট্ৰেক মেৰামতি কাম"
    },
    "significant rainfall": {
        "en": "significant rainfall",
        "hi": "भारी बारिश",
        "bn": "ভারী বৃষ্টিপাত",
        "te": "భారీ వర్షం",
        "mr": "मुसळधार पाऊस",
        "ta": "கனமழை",
        "gu": "ભારે વરસાદ",
        "ur": "شدید بارش",
        "kn": "ಭಾರಿ ಮಳೆ",
        "or": "ପ୍ରବଳ ବର୍ଷା",
        "ml": "കനത്ത മഴ",
        "pa": "ਭਾਰੀ ਮੀਂਹ",
        "as": "প্ৰৱল বৰষুণ"
    },
    "low visibility": {
        "en": "low visibility",
        "hi": "कम दृश्यता व कोहरा",
        "bn": "কম দৃশ্যমানতা ও কুয়াশা",
        "te": "తక్కువ దృశ్యమానత மற்றும் పొగమంచు",
        "mr": "कमी दृश्यमानता आणि धुके",
        "ta": "குறைந்த பார்வைத் திறன்",
        "gu": "ઓછી દૃશ્યતા અને ધુમ્મસ",
        "ur": "کم حد نگاہ اور کہرا",
        "kn": "ಕಡಿಮೆ ಗೋಚರತೆ ಮತ್ತು ಮಂಜು",
        "or": "କମ୍ ଦୃଶ୍ୟମାନତା",
        "ml": "കുറഞ്ഞ കാഴ്ച പരിധി",
        "pa": "ਘੱਟ ਦਿੱਖ ਅਤੇ ਧੁੰਦ",
        "as": "কম দৃশ্যমানতা"
    },
    "current and historical operating conditions": {
        "en": "current and historical operating conditions",
        "hi": "परिचालन व लाइन परिस्थितियाँ",
        "bn": "বর্তমান ও ঐতিহাসিক পরিচালন পরিস্থিতি",
        "te": "ప్రస్తుత మరియు చారిత్రక కార్యాచరణ పరిస్థితులు",
        "mr": "सध्याची आणि ऐतिहासिक परिचालन परिस्थिती",
        "ta": "தற்போதைய இயக்க நிலைமைகள்",
        "gu": "વર્તમાન અને ઐતિહાસિક સંચાલન પરિસ્થિતિઓ",
        "ur": "موجودہ اور تاریخی آپریشنل حالات",
        "kn": "ಪ್ರಸ್ತುತ ಮತ್ತು ಐತಿಹಾಸಿಕ ಕಾರ್ಯಾಚರಣೆಯ ಪರಿಸ್ಥಿತಿಗಳು",
        "or": "ବର୍ତ୍ତମାନ ଓ ଐତିହାସିକ ପରିଚାଳନା ସ୍ଥିତି",
        "ml": "നിലവിലെ പ്രവർത്തന സാഹചര്യങ്ങൾ",
        "pa": "ਮੌਜੂਦਾ ਸੰਚਾਲਨ ਹਾਲਾਤ",
        "as": "বৰ্তমান পৰিচালনাৰ পৰিস্থিতি"
    }
}


def localize_delay_reason(reason_str: str, lang: str = "en") -> str:
    if not reason_str:
        return "Normal operating conditions" if lang == "en" else "सामान्य परिचालन परिस्थितियाँ"
    l_code = lang.lower().strip() if lang else "en"
    if l_code not in LANGUAGES:
        l_code = "en"
    if l_code == "en":
        return reason_str

    target_lang = l_code if l_code in ["hi", "bn", "te", "mr", "ta", "gu", "ur", "kn", "or", "ml", "pa", "as"] else "hi"
    r_lower = reason_str.lower()
    matched_items = []
    
    for key, trans_map in REASON_CONTRIBUTORS.items():
        if key in r_lower:
            matched_items.append(trans_map.get(target_lang, trans_map.get("hi", key)))

    # Composite heuristics for arbitrary strings
    if ("low visibility" in r_lower or "visibility" in r_lower) and REASON_CONTRIBUTORS["low visibility"][target_lang] not in matched_items:
        matched_items.append(REASON_CONTRIBUTORS["low visibility"][target_lang])
    if ("reduced speed" in r_lower or "reduced train speed" in r_lower) and REASON_CONTRIBUTORS["reduced current speed"][target_lang] not in matched_items:
        matched_items.append(REASON_CONTRIBUTORS["reduced current speed"][target_lang])
    if ("congestion" in r_lower or "traffic" in r_lower) and REASON_CONTRIBUTORS["high section congestion"][target_lang] not in matched_items:
        matched_items.append(REASON_CONTRIBUTORS["high section congestion"][target_lang])
    if ("maintenance" in r_lower or "track maintenance" in r_lower) and REASON_CONTRIBUTORS["active track maintenance"][target_lang] not in matched_items:
        matched_items.append(REASON_CONTRIBUTORS["active track maintenance"][target_lang])
    if ("rainfall" in r_lower or "rain" in r_lower) and REASON_CONTRIBUTORS["significant rainfall"][target_lang] not in matched_items:
        matched_items.append(REASON_CONTRIBUTORS["significant rainfall"][target_lang])
    if ("trains ahead" in r_lower or "train ahead" in r_lower) and REASON_CONTRIBUTORS["multiple trains ahead"][target_lang] not in matched_items:
        matched_items.append(REASON_CONTRIBUTORS["multiple trains ahead"][target_lang])

    if not matched_items:
        matched_items.append(REASON_CONTRIBUTORS["current and historical operating conditions"][target_lang])

    if target_lang in ["hi", "mr", "gu"]:
        sep = " तथा "
    elif target_lang == "ta":
        sep = " மற்றும் "
    elif target_lang in ["bn", "as"]:
        sep = " এবং "
    else:
        sep = ", "
        
    return sep.join(matched_items)


def _clean_time(t_val):
    if not t_val:
        return "8:47 PM"
    s = str(t_val).strip()
    if "T" in s:
        try:
            time_part = s.split("T")[1]
            parts = time_part.split(":")
            hh = int(parts[0])
            mm = parts[1][:2]
            ampm = "PM" if hh >= 12 else "AM"
            h12 = hh % 12 or 12
            return f"{h12}:{mm} {ampm}"
        except Exception:
            return s
    return s


def labels(lang="en"):
    return LABELS.get(lang, LABELS["en"])


def available_languages():
    return [{"code": k, "name": v} for k, v in LANGUAGES.items()]


def chatbot_reply(query, prediction, lang="en"):
    l_code = lang.lower().strip() if lang else "en"
    if l_code not in CHAT_TEMPLATES:
        l_code = "en"
    tpl = CHAT_TEMPLATES[l_code]

    q = (query or "").lower().strip()
    cur_mins = f"{float(prediction.get('current_delay_mins', 18) or 18):.0f}"
    add_mins = f"{float(prediction.get('predicted_additional_delay_mins', 15) or 15):.0f}"
    raw_reason = prediction.get("delay_reason") or "Low visibility + reduced train speed in this region"
    localized_reason = localize_delay_reason(raw_reason, l_code)
    
    eta = _clean_time(prediction.get("eta", "8:47 PM"))
    eta_int = prediction.get("eta_interval", {})
    lower = _clean_time(eta_int.get("lower", eta))
    upper = _clean_time(eta_int.get("upper", eta))
    status = prediction.get("movement_status", "Running")
    prop = prediction.get("propagation", {})
    risk = prop.get("risk", "LOW")
    prob = float(prop.get("probability", 0.15))

    def has_word(pattern, text):
        return bool(re.search(r'(?i)\b' + pattern + r'\b', text))

    def has_any_sub(keywords, text):
        return any(k in text for k in keywords)

    # 1. Weather / Fog / Rain (avoid matching 'train' for 'rain')
    weather_words = ["weather", "fog", "rain", "rainy", "rainfall", "storm", "visibility"]
    weather_indic = ["मौसम", "कोहरा", "बारिश", "धुंध", "আবহাওয়া", "বৃষ্টি", "কুয়াশা", "వాతావరణం", "వర్షం", "வானிலை", "மழை", "હવામાન", "વરસાદ", "हवामान", "पाऊस", "धुके", "ಹವಾಮಾನ", "ಮಳೆ", "കാലാവസ്ഥ", "മഴ", "ਮੌਸਮ", "ਮੀਂਹ", "ପାଣିପାଗ", "ବର୍ଷା", "বতৰ", "বৰষুণ", "موسم", "بارش"]
    if any(has_word(w, q) for w in weather_words) or has_any_sub(weather_indic, q):
        return tpl["weather"]

    # 2. Delay Reason / Why delayed
    reason_words = ["why", "reason", "cause", "kyun", "kyu"]
    reason_indic = [
        "क्यों", "कारण", "वजह",
        "কেন", "কারণ",
        "ఎందుకు", "కారణం",
        "ஏன்", "காரணம்",
        "શા માટે", "કા", "કારણ",
        "ಯಾಕೆ", "ಕಾರಣ", "ಕಾರಣವೇನು",
        "എന്തുകൊണ്ട്", "കാരണം", "കാരണമെന്ത്",
        "ਕਿਉਂ", "ਕਾਰਨ", "ਕਾਹਤੋਂ",
        "କାହିଁକି", "କାରଣ",
        "কিয়", "কাৰণ",
        "کیوں", "وجہ", "سبب"
    ]
    if any(has_word(w, q) for w in reason_words) or has_any_sub(reason_indic, q):
        return tpl["reason"].format(reason=localized_reason, add_mins=add_mins)

    # 3. Current Delay / How late / Delay duration
    delay_words = ["delay", "delayed", "late", "lateness", "how late", "kitni der"]
    delay_indic = ["देरी", "देर", "विलंब", "लेट", "বিলম্ব", "দেরি", "ఆలస్యం", "లేట్", "தாமதம்", "லேட்", "વિલંબ", "મોડું", "उशीर", "ವಿಳಂಬ", "വൈകൽ", "ਦੇਰੀ", "ବିଳମ୍ବ", "তাখির", "تاخیر"]
    if any(has_word(w, q) for w in delay_words) or has_any_sub(delay_indic, q):
        return tpl["delay"].format(cur_mins=cur_mins, add_mins=add_mins)

    # 4. ETA / Arrival time / When will it reach
    eta_words = ["eta", "arrival", "arrive", "reaches", "reach", "reaching", "when", "time", "kab"]
    eta_indic = ["कब", "समय", "आगमन", "पहुंच", "কখন", "সময়", "পৌঁছাবে", "ఎప్పుడు", "రాక", "సమయం", "எப்போது", "நேரம்", "வருகை", "ક્યારે", "આગમન", "કેव्हा", "वेळ", "ಯಾವಾಗ", "ಸಮಯ", "എപ്പോൾ", "സമയം", "ਕਦੋਂ", "ਸਮਾਂ", "କେତେବେଳେ", "কেতিয়া", "کب", "وقت"]
    if any(has_word(w, q) for w in eta_words) or has_any_sub(eta_indic, q):
        return tpl["eta"].format(eta=eta, lower=lower, upper=upper)

    # 5. Route / Stations / Stops / Progress
    route_words = ["route", "station", "stations", "stop", "stops", "track", "path"]
    route_indic = ["मार्ग", "रूट", "स्टेशन", "পথ", "স্টেশন", "మార్గం", "స్టేషన్", "வழித்தடம்", "நிலையம்", "માર્ગ", "સ્ટેશન", "स्थानक", "ಮಾರ್ಗ", "ನಿಲ್ದಾಣ", "റൂട്ട്", "ਸਟੇਸ਼ਨ", "ਮਾਰਗ", "ৰুট", "راستہ", "اسٹیشن"]
    if any(has_word(w, q) for w in route_words) or has_any_sub(route_indic, q):
        return tpl["route"]

    # 6. Platform
    platform_words = ["platform", "track number"]
    platform_indic = ["प्लेटफॉर्म", "প্ল্যাটফর্ম", "ప్లాట్‌ఫారమ్", "நடைமேடை", "પ્લેટફોર્મ", "प्लॅटफॉर्म", "ಪ್ಲಾಟ್‌ಫಾರ್ಮ್", "പ്ലാറ്റ്‌ഫോം", "ਪਲੇਟਫਾਰਮ", "ପ୍ଲାଟଫର୍ମ", "প্লেটফৰ্ম", "پلیٹ فارم"]
    if any(has_word(w, q) for w in platform_words) or has_any_sub(platform_indic, q):
        return tpl["platform"]

    # 7. Location / Where is train / Status
    where_words = ["where", "location", "status", "position", "kahan"]
    where_indic = ["कहाँ", "कहा", "स्थिति", "জায়গা", "কোথায়", "অবস্থা", "ఎక్కడ", "పరిస్థితి", "எங்கே", "நிலை", "ક્યાં", "સ્થિતિ", "कुठे", "स्थिती", "ಎಲ್ಲಿ", "ಸ್ಥಿತಿ", "എവിടെ", "നില", "ਕਿੱਥੇ", "ਸਥਿਤੀ", "କେଉଁଠି", "ସ୍ଥିତି", "ক'त", "স্থিতি", "کہاں", "صورتحال"]
    if any(has_word(w, q) for w in where_words) or has_any_sub(where_indic, q):
        return tpl["where"].format(status=status)

    # 8. Propagation / Downstream train impacts
    propagation_words = ["propagation", "impact", "network", "cascade", "downstream", "other trains"]
    propagation_indic = ["प्रभाव", "जोखिम", "ছড়ানো", "ঝুঁকি", "ప్రమాదం", "அபாயம்", "જોખમ", "धोका", "ಅಪಾಯ", "ആപത്ത്", "ਖਤਰਾ", "ଆଶଙ୍କା", "বিপদ", "خطرہ"]
    if any(has_word(w, q) for w in propagation_words) or has_any_sub(propagation_indic, q):
        return tpl["propagation"].format(risk=risk, prob=prob)

    # Default fallback
    return tpl["fallback"]
