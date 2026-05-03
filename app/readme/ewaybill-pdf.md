# E-Way Bill PDF — Integration Guide

Generates a print-ready A4 black & white PDF for any validated E-Way Bill.  
Includes QR code (top-right), all 5 NIC sections, and a Code128 barcode at the bottom.

---

## API Endpoint

```
GET /v1/ewaybill/pdf?eway_bill_number={12-digit-EWB-number}&token={jwt}
```

| Parameter | Type | Required | Description |
|---|---|---|---|
| `eway_bill_number` | string | ✅ | 12-digit E-Way Bill number |
| `token` | string | ⚠️ see below | JWT access token — required when using direct browser links |

**Auth — two ways to pass the JWT:**

| Method | When to use |
|---|---|
| `Authorization: Bearer <token>` header | `fetch()` / axios calls |
| `?token=<jwt>` query parameter | `window.open()`, `<a href>`, direct browser navigation |

Browsers cannot attach custom headers to plain URL navigations. Pass `?token=` for any direct link.

**Response:** `application/pdf` binary stream with header:
```
Content-Disposition: inline; filename="EWB_441719091297.pdf"
```

**Data source:** The endpoint first checks `ewb_records` DB table.  
If not found, it fetches live from NIC, saves to DB, then generates the PDF.  
No extra backend call needed from the frontend.

---

## Frontend Integration

### 1. Download Button

Opens a Save dialog so the user can save the PDF file locally.

```jsx
const downloadEWB = (ewbNumber, token) => {
  // Pass token as query param — browsers can't add headers to anchor clicks
  const url = `/v1/ewaybill/pdf?eway_bill_number=${ewbNumber}&token=${token}`;
  const a   = document.createElement("a");
  a.href     = url;
  a.download = `EWB_${ewbNumber}.pdf`;
  a.click();
};
```

**React button example:**
```jsx
<button onClick={() => downloadEWB(ewbNumber, authToken)}>
  Download EWB PDF
</button>
```

---

### 2. Print Button

Opens the PDF in a new browser tab and triggers the browser print dialog immediately.

```jsx
const printEWB = (ewbNumber, token) => {
  // Pass token as query param — window.open cannot set headers
  const url = `/v1/ewaybill/pdf?eway_bill_number=${ewbNumber}&token=${token}`;
  window.open(url, "_blank");
  // The browser's built-in PDF viewer handles printing from there
};
```

**React button example:**
```jsx
<button onClick={() => printEWB(ewbNumber, authToken)}>
  Print EWB
</button>
```

---

### 3. Both Buttons Together (React component)

Since both actions use direct browser navigation (no `fetch`), no loading state is needed — the browser handles everything.

```jsx
export function EWBActions({ ewbNumber, token }) {
  const pdfUrl = `/v1/ewaybill/pdf?eway_bill_number=${ewbNumber}&token=${token}`;

  const handlePrint = () => {
    window.open(pdfUrl, "_blank");
  };

  const handleDownload = () => {
    const a    = document.createElement("a");
    a.href     = pdfUrl;
    a.download = `EWB_${ewbNumber}.pdf`;
    a.click();
  };

  return (
    <div style={{ display: "flex", gap: "8px" }}>
      <button onClick={handlePrint}>🖨 Print EWB</button>
      <button onClick={handleDownload}>⬇ Download PDF</button>
    </div>
  );
}
```

**Usage:**
```jsx
<EWBActions ewbNumber="441719091297" token={authToken} />
```

> **Where to get `authToken`:** Read it from wherever your app stores the JWT after login — e.g. `localStorage.getItem('access_token')`, Zustand/Redux store, or React context.

---

## PDF Layout

The generated PDF matches the official NIC EWB print format:

| # | Section | Contents |
|---|---|---|
| Header | e-Way Bill title + QR code | EWB number, date, validity, status encoded in QR |
| 1 | E-WAY BILL Details | EWB no, mode, type, generated date, distance, document details, valid upto |
| 2 | Address Details | From GSTIN/address and To GSTIN/address side by side |
| 3 | Goods Details | Item table: HSN code, description, qty, taxable amount, tax rates. Totals summary below |
| 4 | Transportation Details | Transporter ID, name, doc no & date |
| 5 | Vehicle Details | Mode, vehicle number, from place, entered date, entered by (shown only if vehicle data exists) |
| Footer | Barcode | Code128 barcode of the EWB number, scannable |

---

## Notes

- **No extra validation step needed** — if the EWB was already fetched/generated through the app, the PDF is served from DB instantly.
- **First-time fetch** — if the EWB number was never loaded in the app before, it is fetched live from NIC (adds ~1-2 seconds).
- **Print settings** — advise users to set paper size to **A4**, margins to **minimum/none**, and enable **Background graphics** off for clean B&W output.
- The PDF is served with `Content-Disposition: inline` so browsers open it in the PDF viewer tab rather than auto-downloading.
