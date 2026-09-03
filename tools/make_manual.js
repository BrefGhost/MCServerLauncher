// Builds docs/คู่มือการใช้งาน.docx — the printable Thai user manual.
//
// Written for someone who has never run a Minecraft server: every step says
// what to click, and every warning says what it will cost them if ignored.
const fs = require("fs");
const path = require("path");
const {
  AlignmentType, BorderStyle, Document, HeadingLevel, ImageRun, LevelFormat,
  Packer, PageBreak, Paragraph, ShadingType, Table, TableCell, TableRow,
  TextRun, WidthType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const THAI = "Leelawadee UI";
const GREEN = "3E8E41";
const GREY = "5B6472";
const TABLE_W = 9000;          // DXA, fits A4 with the default margins

const P = (text, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 120, line: 300 },
  alignment: opts.align,
  children: [new TextRun({
    text, font: THAI, size: opts.size ?? 22,
    bold: opts.bold, italics: opts.italics,
    color: opts.color,
  })],
});

const H = (text, level) => new Paragraph({
  heading: level,
  spacing: { before: 280, after: 140 },
  children: [new TextRun({ text, font: THAI, bold: true,
                           size: level === HeadingLevel.HEADING_1 ? 32 : 26,
                           color: level === HeadingLevel.HEADING_1 ? GREEN : "222222" })],
});

const Bullet = (text, level = 0) => new Paragraph({
  numbering: { reference: "dots", level },
  spacing: { after: 80, line: 300 },
  children: [new TextRun({ text, font: THAI, size: 22 })],
});

const Step = (text) => new Paragraph({
  numbering: { reference: "steps", level: 0 },
  spacing: { after: 100, line: 300 },
  children: [new TextRun({ text, font: THAI, size: 22 })],
});

const Code = (text) => new Paragraph({
  spacing: { after: 120, line: 260 },
  shading: { type: ShadingType.CLEAR, fill: "F1F3F5" },
  children: [new TextRun({ text, font: "Consolas", size: 20 })],
});

const Note = (label, text) => new Paragraph({
  spacing: { before: 120, after: 160, line: 300 },
  shading: { type: ShadingType.CLEAR, fill: "FFF6E5" },
  border: { left: { style: BorderStyle.SINGLE, size: 18, color: "E0A93B", space: 8 } },
  children: [
    new TextRun({ text: label + "  ", font: THAI, size: 22, bold: true, color: "9A6A00" }),
    new TextRun({ text, font: THAI, size: 22 }),
  ],
});

function table(headers, rows, widths) {
  const cell = (text, opts = {}) => new TableCell({
    width: { size: opts.w, type: WidthType.DXA },
    shading: opts.head
      ? { type: ShadingType.CLEAR, fill: "E8F2E9" }
      : { type: ShadingType.CLEAR, fill: "FFFFFF" },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({
      spacing: { after: 0, line: 280 },
      children: [new TextRun({ text, font: THAI, size: 21, bold: opts.head })],
    })],
  });
  return new Table({
    columnWidths: widths,
    width: { size: TABLE_W, type: WidthType.DXA },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headers.map((h, i) => cell(h, { w: widths[i], head: true })),
      }),
      ...rows.map((r) => new TableRow({
        children: r.map((c, i) => cell(c, { w: widths[i] })),
      })),
    ],
  });
}

const children = [];

// ---------------------------------------------------------------- cover ----
const iconPath = path.join(ROOT, "assets", "icon.png");
if (fs.existsSync(iconPath)) {
  children.push(new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 1600, after: 240 },
    children: [new ImageRun({
      type: "png", data: fs.readFileSync(iconPath),
      transformation: { width: 120, height: 120 },
    })],
  }));
}
children.push(
  P("MC Server Launcher", { size: 52, bold: true, align: AlignmentType.CENTER, after: 80 }),
  P("คู่มือการติดตั้งและการใช้งาน", { size: 30, align: AlignmentType.CENTER, color: GREY, after: 40 }),
  P("เวอร์ชัน 1.0", { size: 24, align: AlignmentType.CENTER, color: GREY, after: 900 }),
  P("เปิดเซิร์ฟเวอร์ Minecraft จาก modpack ที่คุณเล่นอยู่ ให้เพื่อนเข้ามาเล่นด้วยกันได้",
    { align: AlignmentType.CENTER, color: GREY, after: 0 }),
  P("โดยไม่ต้องแตะไฟล์ ไม่ต้องตั้งค่า router และไม่ต้องรู้เรื่องเซิร์ฟเวอร์มาก่อน",
    { align: AlignmentType.CENTER, color: GREY }),
  new Paragraph({ children: [new PageBreak()] }),
);

// -------------------------------------------------------------- contents ---
children.push(
  H("สารบัญ", HeadingLevel.HEADING_1),
  Bullet("1. โปรแกรมนี้ทำอะไร"),
  Bullet("2. สิ่งที่ต้องมีก่อนใช้งาน"),
  Bullet("3. การติดตั้ง"),
  Bullet("4. การตั้งค่าครั้งแรก"),
  Bullet("5. วิธีใช้งาน"),
  Bullet("6. คำอธิบายการตั้งค่าแต่ละอย่าง"),
  Bullet("7. ไฟล์ต่าง ๆ ถูกเก็บไว้ที่ไหน"),
  Bullet("8. ปัญหาที่พบบ่อยและวิธีแก้"),
  Bullet("9. ข้อจำกัดที่ควรรู้"),
  new Paragraph({ children: [new PageBreak()] }),
);

// ------------------------------------------------------------- 1 what -----
children.push(
  H("1. โปรแกรมนี้ทำอะไร", HeadingLevel.HEADING_1),
  P("ปกติถ้าจะเปิดเซิร์ฟเวอร์ Minecraft จาก modpack เอง คุณต้องทำหลายขั้นตอนที่ยุ่งยาก คือ หาไฟล์ติดตั้ง Forge หรือ NeoForge ให้ตรงเวอร์ชัน สั่งติดตั้งผ่าน command line คัดลอกม็อดและไฟล์ตั้งค่าไปยังโฟลเดอร์เซิร์ฟเวอร์ แก้ไฟล์ eula.txt และ server.properties ด้วยมือ แล้วยังต้องตั้งค่า router เพื่อให้เพื่อนต่อเข้ามาได้"),
  P("โปรแกรมนี้ทำขั้นตอนทั้งหมดนั้นแทนคุณ เหลือแค่ลากโฟลเดอร์ modpack มาวางในหน้าต่างโปรแกรม"),
  H("โปรแกรมทำอะไรให้บ้าง", HeadingLevel.HEADING_2),
  table(
    ["ขั้นตอน", "รายละเอียด"],
    [
      ["หา Java ที่ถูกเวอร์ชัน", "Minecraft แต่ละเวอร์ชันใช้ Java คนละรุ่น โปรแกรมเลือกให้เองจาก Java ที่มีอยู่ในเครื่องแล้ว"],
      ["ติดตั้งเซิร์ฟเวอร์", "ดาวน์โหลดตัวติดตั้ง Forge หรือ NeoForge รุ่นที่ตรงกับ modpack จากเว็บทางการ แล้วติดตั้งให้"],
      ["ใส่ม็อดและไฟล์ตั้งค่า", "คัดลอกม็อดทุกตัวและโฟลเดอร์เนื้อหาของแพ็คไปยังเซิร์ฟเวอร์"],
      ["จัดการม็อดที่เซิร์ฟเวอร์รับไม่ได้", "ม็อดบางตัวทำงานได้เฉพาะในเกม ถ้าเซิร์ฟเวอร์แจ้งว่ารับไม่ได้ โปรแกรมจะเอาออกให้แล้วเปิดใหม่"],
      ["เปิดให้เพื่อนต่อจากข้างนอก", "ใช้บริการ playit.gg เจาะออกจากเน็ตบ้าน ไม่ต้องตั้งค่า router"],
      ["บอกที่อยู่เซิร์ฟเวอร์", "ดึงที่อยู่สาธารณะมาแสดงให้เอง กดปุ่มก๊อปแล้วส่งให้เพื่อนได้เลย"],
      ["ปิดอย่างปลอดภัย", "สั่งให้เซิร์ฟเวอร์บันทึกโลกก่อนปิดเสมอ ไม่ใช่ปิดดื้อ ๆ"],
    ],
    [2600, 6400],
  ),
  new Paragraph({ children: [new PageBreak()] }),
);

// ------------------------------------------------------- 2 requirements ---
children.push(
  H("2. สิ่งที่ต้องมีก่อนใช้งาน", HeadingLevel.HEADING_1),
  table(
    ["สิ่งที่ต้องมี", "รายละเอียด"],
    [
      ["Windows", "Windows 10 หรือ 11 (64-bit)"],
      ["modpack ที่ติดตั้งแล้ว", "จาก CurseForge, Modrinth, MultiMC หรือ Prism Launcher ก็ได้"],
      ["Java", "ปกติมีอยู่แล้วเพราะ CurseForge ติดตั้งมาให้ตอนลงเกม ถ้าไม่มีโปรแกรมจะแจ้งเตือน"],
      ["แรม", "อย่างน้อย 8 GB แนะนำ 16 GB ขึ้นไปถ้าจะเล่นเกมบนเครื่องเดียวกันด้วย"],
      ["พื้นที่ว่าง", "ประมาณ 2–5 GB ต่อ modpack หนึ่งชุด"],
      ["อินเทอร์เน็ต", "ใช้ตอนดาวน์โหลดตัวติดตั้งครั้งแรก และตอนเปิดให้เพื่อนต่อเข้ามา"],
      ["บัญชี playit.gg", "สมัครฟรี ใช้เฉพาะกรณีที่ต้องการให้เพื่อนนอกบ้านเข้ามาเล่นได้"],
    ],
    [2600, 6400],
  ),
  Note("ข้อควรระวัง",
    "ถ้าจะเปิดเซิร์ฟเวอร์และเล่นเกมบนเครื่องเดียวกัน ให้ดูแรมรวมด้วย ตัวเกมเองกินได้ถึง 10–14 GB ถ้าตั้งแรมเซิร์ฟเวอร์สูงเกินไป ทั้งเกมและเซิร์ฟเวอร์จะช้าลงพร้อมกัน"),
  new Paragraph({ children: [new PageBreak()] }),
);

// -------------------------------------------------------- 3 installation --
children.push(
  H("3. การติดตั้ง", HeadingLevel.HEADING_1),
  H("วิธีที่ 1 ใช้ไฟล์ .exe (แนะนำ)", HeadingLevel.HEADING_2),
  Step("ดาวน์โหลดไฟล์ MC Server Launcher.exe"),
  Step("วางไว้ในโฟลเดอร์ที่มีพื้นที่ว่างพอ เช่น D:\\MCServer เพราะโปรแกรมจะสร้างโฟลเดอร์เก็บเซิร์ฟเวอร์ไว้ข้าง ๆ ไฟล์นี้"),
  Step("ดับเบิลคลิกเพื่อเปิด ไม่ต้องติดตั้งอะไรเพิ่ม"),
  Note("Windows อาจเตือน",
    "ครั้งแรกที่เปิด Windows SmartScreen อาจขึ้นว่า \"Windows protected your PC\" เพราะไฟล์ยังไม่มีลายเซ็นดิจิทัล ให้กด More info แล้วกด Run anyway"),
  H("วิธีที่ 2 รันจากซอร์สโค้ด", HeadingLevel.HEADING_2),
  P("เหมาะกับกรณีที่อยากแก้ไขโปรแกรมเอง ต้องมี Python 3.10 ขึ้นไป"),
  Code("git clone https://github.com/BrefGhost/MCServerLauncher.git"),
  Code("cd MCServerLauncher"),
  Code("เปิดโปรแกรม.bat"),
  new Paragraph({ children: [new PageBreak()] }),
);

// ----------------------------------------------------------- 4 first run --
children.push(
  H("4. การตั้งค่าครั้งแรก", HeadingLevel.HEADING_1),
  H("4.1 ยอมรับ Minecraft EULA", HeadingLevel.HEADING_2),
  P("Mojang กำหนดว่าเซิร์ฟเวอร์ Minecraft ทุกเครื่องต้องยอมรับข้อตกลงการใช้งานก่อนถึงจะเปิดได้ ในหน้าต่างโปรแกรมมุมล่างซ้าย ให้ติ๊กช่อง \"ยอมรับ Minecraft EULA\" ทำครั้งเดียวจบ กดที่ข้อความ Minecraft EULA เพื่ออ่านฉบับเต็มได้"),
  H("4.2 อนุมัติ playit.gg", HeadingLevel.HEADING_2),
  P("ขั้นตอนนี้ทำเฉพาะกรณีที่ต้องการให้เพื่อนนอกบ้านเข้ามาเล่น ทำครั้งเดียวเช่นกัน"),
  Step("กดเริ่มเซิร์ฟเวอร์ตามปกติ"),
  Step("โปรแกรมจะเปิดหน้าเว็บ playit.gg ขึ้นมาเอง"),
  Step("สมัครบัญชีหรือเข้าสู่ระบบ แล้วกดปุ่มอนุมัติ"),
  Step("กลับมาที่โปรแกรม รอสักครู่ ที่อยู่เซิร์ฟเวอร์จะขึ้นมาเอง"),
  P("หลังจากนี้โปรแกรมจะจำบัญชีไว้ ครั้งต่อไปไม่ต้องทำอะไรอีก"),
  Note("ทำไมต้องใช้ playit.gg",
    "เน็ตบ้านในไทยส่วนใหญ่ไม่มีหมายเลข IP สาธารณะเป็นของตัวเอง เพื่อนจึงต่อตรงเข้าเครื่องคุณไม่ได้ playit.gg ทำหน้าที่เป็นทางผ่านให้ฟรี แลกกับการที่ข้อมูลทั้งหมดวิ่งผ่านเซิร์ฟเวอร์ของเขา"),
  new Paragraph({ children: [new PageBreak()] }),
);

// ---------------------------------------------------------------- 5 use ---
children.push(
  H("5. วิธีใช้งาน", HeadingLevel.HEADING_1),
  H("เปิดเซิร์ฟเวอร์", HeadingLevel.HEADING_2),
  Step("เปิดโปรแกรม"),
  Step("ลากโฟลเดอร์ modpack มาวางในหน้าต่างโปรแกรม หรือเลือกจากรายการที่โปรแกรมสแกนเจอเอง"),
  Step("ถ้าติ๊ก EULA ไว้แล้ว เซิร์ฟเวอร์จะเริ่มทำงานทันทีที่ลากเสร็จ ถ้ายังไม่ติ๊ก ให้ติ๊กแล้วกดปุ่ม เริ่มเซิร์ฟเวอร์"),
  Step("รอจนช่อง ที่อยู่เซิร์ฟเวอร์ แสดงที่อยู่ขึ้นมา"),
  Step("กดปุ่ม ก๊อป แล้วส่งที่อยู่นั้นให้เพื่อน"),
  P("การเปิดครั้งแรกของแต่ละแพ็คใช้เวลาประมาณ 2–5 นาที เพราะต้องติดตั้งเซิร์ฟเวอร์และคัดม็อดที่เซิร์ฟเวอร์รับไม่ได้ออก ครั้งต่อไปจะเร็วขึ้นมาก"),
  H("เพื่อนเข้าเซิร์ฟเวอร์อย่างไร", HeadingLevel.HEADING_2),
  Step("เปิด Minecraft ด้วย modpack ตัวเดียวกันและเวอร์ชันเดียวกัน"),
  Step("เลือก Multiplayer แล้วกด Add Server"),
  Step("วางที่อยู่ที่คุณส่งให้ลงในช่อง Server Address แล้วกด Done"),
  Step("กด Join Server"),
  Note("สำคัญ", "เพื่อนต้องใช้ modpack ชุดเดียวกันและเวอร์ชันเดียวกันกับที่เปิดเซิร์ฟเวอร์ ถ้าคนละเวอร์ชันจะเข้าไม่ได้"),
  H("ปิดเซิร์ฟเวอร์", HeadingLevel.HEADING_2),
  P("กดปุ่ม หยุดเซิร์ฟเวอร์ โปรแกรมจะสั่งให้เซิร์ฟเวอร์บันทึกโลกให้เรียบร้อยก่อนปิด อย่าปิดโปรแกรมทิ้งดื้อ ๆ ระหว่างที่เซิร์ฟเวอร์ทำงาน เพราะโลกอาจเสียหายได้"),
  H("สั่งคำสั่งเซิร์ฟเวอร์", HeadingLevel.HEADING_2),
  P("ช่องด้านล่างของหน้าต่างใช้พิมพ์คำสั่งเซิร์ฟเวอร์ได้โดยตรง เช่น"),
  Code("op ชื่อผู้เล่น       ให้สิทธิ์แอดมิน"),
  Code("weather clear      เปลี่ยนสภาพอากาศ"),
  Code("time set day       เปลี่ยนเวลาเป็นกลางวัน"),
  Code("say ข้อความ         ประกาศข้อความให้ทุกคนเห็น"),
  new Paragraph({ children: [new PageBreak()] }),
);

// ----------------------------------------------------------- 6 settings ---
children.push(
  H("6. คำอธิบายการตั้งค่าแต่ละอย่าง", HeadingLevel.HEADING_1),
  P("ในหน้าต่างโปรแกรม ทุกหัวข้อจะมีเครื่องหมาย ? อยู่ข้าง ๆ เอาเมาส์ไปชี้เพื่อดูคำอธิบายได้ทันที ตารางนี้คือคำอธิบายฉบับเต็ม"),
  table(
    ["การตั้งค่า", "ความหมายและคำแนะนำ"],
    [
      ["modpack", "แพ็คที่จะเปิดเป็นเซิร์ฟเวอร์ เซิร์ฟเวอร์กับเกมต้องเป็นแพ็คเวอร์ชันเดียวกัน ถ้าอัปเดตแพ็คในเกมแล้วให้กดเริ่มเซิร์ฟเวอร์ใหม่"],
      ["แรมที่ให้เซิร์ฟเวอร์", "แพ็คใหญ่ตั้งแต่ 200 ม็อดขึ้นไปควรให้ 8 GB ขึ้นไป ถ้าเล่นเกมบนเครื่องเดียวกันด้วย อย่าให้เกินครึ่งหนึ่งของแรมทั้งเครื่อง"],
      ["จำนวนผู้เล่นสูงสุด", "จำนวนคนที่เข้าพร้อมกันได้"],
      ["ความยาก", "สงบคือไม่มีมอนสเตอร์และไม่หิว ง่าย ปกติ ยาก คือมอนสเตอร์แรงขึ้นตามลำดับ เปลี่ยนทีหลังได้"],
      ["ข้อความหน้าเซิร์ฟ", "ข้อความที่เพื่อนเห็นใต้ชื่อเซิร์ฟเวอร์ในหน้ารายชื่อเซิร์ฟเวอร์"],
      ["แอดมิน", "ชื่อผู้เล่นที่จะใช้คำสั่งอย่าง /gamemode /tp /give ได้ ใส่ชื่อในเกมของคุณเองไว้ด้วย ใส่หลายคนได้โดยเว้นวรรค"],
      ["โลก", "สร้างโลกใหม่ หรือเอาโลกที่เคยเล่นคนเดียวมาเปิดเป็นเซิร์ฟเวอร์ก็ได้ โปรแกรมคัดลอกมา ไม่ได้ย้ายไฟล์ต้นฉบับ"],
      ["ให้เพื่อนต่อจากข้างนอกได้", "เปิดไว้ถ้าต้องการให้คนนอกบ้านเข้าได้ ถ้าปิดจะเล่นได้เฉพาะคนที่ต่อ Wi-Fi เดียวกัน"],
      ["ต้องเป็นบัญชี Minecraft แท้", "แนะนำให้เปิดไว้ ถ้าปิดใครก็ตั้งชื่อเป็นใครก็ได้แล้วเข้ามา รวมถึงสวมชื่อคุณเอง"],
    ],
    [2600, 6400],
  ),
  new Paragraph({ children: [new PageBreak()] }),
);

// -------------------------------------------------------------- 7 files ---
children.push(
  H("7. ไฟล์ต่าง ๆ ถูกเก็บไว้ที่ไหน", HeadingLevel.HEADING_1),
  P("โปรแกรมสร้างโฟลเดอร์เหล่านี้ไว้ข้างไฟล์ .exe"),
  table(
    ["โฟลเดอร์", "เก็บอะไร"],
    [
      ["servers", "ตัวเซิร์ฟเวอร์จริงของแต่ละแพ็ค รวมถึงโลกที่เล่น อยู่ในนี้ทั้งหมด"],
      ["logs", "บันทึกการทำงานของโปรแกรม ถ้าเจอปัญหาให้ส่งไฟล์ในนี้มาให้ดู"],
      ["data", "ค่าตั้งของโปรแกรมและกุญแจบัญชี playit.gg"],
      ["cache", "ตัวติดตั้งที่ดาวน์โหลดมา ลบทิ้งได้ถ้าต้องการพื้นที่คืน"],
    ],
    [2600, 6400],
  ),
  Note("อย่าแชร์โฟลเดอร์ data",
    "ในนั้นมีไฟล์ playit_secret.txt ซึ่งเป็นกุญแจบัญชี playit.gg ของคุณ ใครได้ไปสามารถใช้บัญชีคุณเปิดช่องทางเชื่อมต่อได้"),
  P("โลกที่เล่นอยู่ในโฟลเดอร์ servers ชื่อแพ็ค world ถ้าจะสำรองโลกให้คัดลอกโฟลเดอร์นั้นเก็บไว้"),
  new Paragraph({ children: [new PageBreak()] }),
);

// ----------------------------------------------------- 8 troubleshooting --
children.push(
  H("8. ปัญหาที่พบบ่อยและวิธีแก้", HeadingLevel.HEADING_1),
  table(
    ["อาการ", "วิธีแก้"],
    [
      ["เปิดโปรแกรมแล้วไม่เห็น modpack",
       "กดปุ่ม สแกนใหม่ ถ้ายังไม่เห็นให้ลากโฟลเดอร์ของแพ็คมาวางในหน้าต่างโดยตรง โฟลเดอร์นั้นต้องมีไฟล์ minecraftinstance.json manifest.json หรือ mmc-pack.json อยู่"],
      ["เซิร์ฟเวอร์เปิดแล้วปิดเองหลายรอบ",
       "เป็นเรื่องปกติของการเปิดครั้งแรก เซิร์ฟเวอร์กำลังบอกว่ารับม็อดตัวไหนไม่ได้ ปล่อยให้ทำงานไป ถ้าครบ 25 รอบแล้วยังไม่ขึ้นให้ดูไฟล์ใน logs"],
      ["เพื่อนขึ้นว่า mismatched mod channel list",
       "แปลว่าม็อดสองฝั่งไม่ตรงกัน ให้ตรวจว่าเพื่อนใช้แพ็คเวอร์ชันเดียวกันจริง"],
      ["เพื่อนค้างที่หน้า Logging in นาน ๆ แล้วหลุด",
       "การซิงก์ข้อมูลม็อดใช้เวลานานเกินกำหนดของเกม ลองให้เพื่อนกดเข้าใหม่อีกครั้ง ถ้ายังไม่ได้ให้ลองปิดเกมของคุณเองก่อนเพื่อคืนแรม"],
      ["ไม่มีที่อยู่เซิร์ฟเวอร์ขึ้นมา",
       "ตรวจว่าติ๊ก ให้เพื่อนต่อจากข้างนอกได้ ไว้แล้ว และดูใน console ว่ามีลิงก์ playit.gg ให้กดอนุมัติหรือไม่"],
      ["โลกหายหลังอัปเดตโปรแกรม",
       "โลกอยู่ในโฟลเดอร์ servers ข้างไฟล์ .exe ถ้าย้าย .exe ไปที่อื่นต้องย้ายโฟลเดอร์ servers ตามไปด้วย"],
    ],
    [2800, 6200],
  ),
  P("ถ้าแก้ไม่ได้ ให้ส่งไฟล์สองอันนี้มาให้ดู"),
  Bullet("logs\\launcher-ชื่อแพ็ค.log  บันทึกของตัวโปรแกรม"),
  Bullet("servers\\ชื่อแพ็ค\\logs\\latest.log  บันทึกของเซิร์ฟเวอร์"),
  new Paragraph({ children: [new PageBreak()] }),
);

// ------------------------------------------------------------ 9 limits ----
children.push(
  H("9. ข้อจำกัดที่ควรรู้", HeadingLevel.HEADING_1),
  Bullet("ใช้ได้กับ Windows เท่านั้น"),
  Bullet("รองรับ modpack ที่ใช้ Forge และ NeoForge ยังไม่รองรับ Fabric หรือ Quilt แบบเดี่ยว ๆ"),
  Bullet("การเปิดครั้งแรกของแต่ละแพ็คต้องเปิดปิดซ้ำ 2–3 รอบ เพราะต้องรอให้เซิร์ฟเวอร์บอกเองว่ารับม็อดตัวไหนไม่ได้ ไม่มีวิธีรู้ล่วงหน้าที่แม่นยำ"),
  Bullet("ข้อมูลทั้งหมดวิ่งผ่านเซิร์ฟเวอร์ของ playit.gg ซึ่งเป็นบริการฟรีจากภายนอก"),
  Bullet("ที่อยู่เซิร์ฟเวอร์อาจเปลี่ยนได้ ให้ส่งที่อยู่ล่าสุดที่โปรแกรมแสดงให้เพื่อนเสมอ"),
  Bullet("ม็อดที่ทำให้เซิร์ฟเวอร์พังหลังเล่นไปแล้ว โปรแกรมยังตรวจจับไม่ได้ ตรวจได้เฉพาะตอนเปิดเซิร์ฟเวอร์"),
  H("เครดิต", HeadingLevel.HEADING_2),
  Bullet("ค่าปรับแต่งหน่วยความจำใช้แนวทาง Aikar's flags"),
  Bullet("การเชื่อมต่อจากภายนอกใช้บริการของ playit.gg"),
  Bullet("Minecraft เป็นเครื่องหมายการค้าของ Mojang Studios โปรแกรมนี้ไม่มีส่วนเกี่ยวข้องกับ Mojang หรือ Microsoft"),
);

const doc = new Document({
  creator: "MC Server Launcher",
  title: "คู่มือการใช้งาน MC Server Launcher",
  description: "คู่มือการติดตั้งและการใช้งาน MC Server Launcher เวอร์ชัน 1.0",
  styles: {
    default: {
      document: { run: { font: THAI, size: 22 } },
    },
  },
  numbering: {
    config: [
      { reference: "dots", levels: [{ level: 0, format: LevelFormat.BULLET, text: "\u2022",
        style: { paragraph: { indent: { left: 460, hanging: 240 } } } }] },
      { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.",
        style: { paragraph: { indent: { left: 460, hanging: 260 } } } }] },
    ],
  },
  sections: [{ properties: {}, children }],
});

const out = path.join(ROOT, "docs", "คู่มือการใช้งาน.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log("เขียนแล้ว:", out, (buf.length / 1024).toFixed(0) + " KB");
});
