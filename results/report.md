# Extraction benchmark report

Run: 2026-10-30 20:58 · 96 synthetic documents · LLM: `gpt-5.4-nano` (effort `low`)

All numbers below were measured in this run. Documents are synthetic (fictional patients, prescribers and DINs); see the README for what that does and does not tell you.

## Headline

| Pipeline | Field accuracy | Critical-field accuracy | Docs 100% correct | Wrong fields | Silent errors | p50 latency | p90 latency | Cost / 1K docs |
|---|---|---|---|---|---|---|---|---|
| `ocr_regex` | 50.9% | 46.9% | 26.0% | 961 | 91 | 405 ms | 845 ms | $0.00 |
| `ocr_reference` | 65.8% | 61.8% | 31.2% | 668 | 50 | 800 ms | 1340 ms | $0.00 |
| `ocr_text_llm` | 62.8% | 65.0% | 19.8% | 751 | 380 | 3722 ms | 9608 ms | $0.79 |
| `vision_llm` | 91.9% | 92.9% | 42.7% | 159 | 129 | 4066 ms | 8069 ms | $1.16 |
| `vision_verified` | 91.9% | 92.9% | 42.7% | 159 | 67 | 4066 ms | 8069 ms | $1.16 |

Critical fields: drug name, strength, sig, quantity, DIN, quantity shipped, unit cost, line total, invoice total, claim status, plan pays, patient pays, response codes. "Silent errors" = a filled-in but wrong value with no review flag - the kind that reaches a patient or a ledger (blank fields are excluded because a reviewer can see them).

## Accuracy by degradation

| Pipeline | clean | skew | blur | noise | fax | low_res |
|---|---|---|---|---|---|---|
| `ocr_regex` | 91.4% | 77.6% | 43.2% | 1.8% | 25.2% | 64.9% |
| `ocr_reference` | 93.5% | 81.8% | 45.8% | 60.7% | 32.2% | 81.3% |
| `ocr_text_llm` | 86.4% | 86.2% | 65.4% | 14.4% | 41.7% | 88.0% |
| `vision_llm` | 97.6% | 95.0% | 92.0% | 95.7% | 71.8% | 97.7% |
| `vision_verified` | 97.6% | 95.0% | 92.0% | 95.7% | 71.8% | 97.7% |

## Accuracy by document style

| Pipeline | Handwritten Rx pad | EMR-printed Rx | Wholesaler invoice | Claim response |
|---|---|---|---|---|
| `ocr_regex` | 36.2% | 70.6% | 38.0% | 71.0% |
| `ocr_reference` | 55.4% | 88.6% | 48.7% | 89.5% |
| `ocr_text_llm` | 60.1% | 84.3% | 49.0% | 77.2% |
| `vision_llm` | 85.1% | 93.9% | 94.0% | 89.5% |
| `vision_verified` | 85.1% | 93.9% | 94.0% | 89.5% |

## Accuracy per field

| Field | `ocr_regex` | `ocr_reference` | `ocr_text_llm` | `vision_llm` | `vision_verified` |
|---|---|---|---|---|---|
| carrier | 62.5% | 75.0% | 58.3% | 79.2% | 79.2% |
| group_number | 58.3% | 70.8% | 70.8% | 83.3% | 83.3% |
| patient_name | 56.9% | 69.4% | 61.1% | 87.5% | 87.5% |
| certificate_id | 54.2% | 70.8% | 79.2% | 87.5% | 87.5% |
| rx_number | 50.0% | 75.0% | 70.8% | 91.7% | 91.7% |
| date_of_service | 83.3% | 100.0% | 95.8% | 100.0% | 100.0% |
| din | 37.3% | 49.7% | 52.5% | 80.4% | 80.4% |
| drug_name | 71.7% | 92.4% | 87.6% | 94.3% | 94.3% |
| strength | 68.9% | 90.5% | 80.0% | 96.2% | 96.2% |
| quantity | 58.1% | 81.9% | 80.0% | 94.3% | 94.3% |
| days_supply | 75.0% | 95.8% | 75.0% | 95.8% | 95.8% |
| total_submitted | 70.8% | 95.8% | 79.2% | 87.5% | 87.5% |
| amount_paid | 79.2% | 95.8% | 79.2% | 87.5% | 87.5% |
| patient_pays | 75.0% | 91.7% | 75.0% | 75.0% | 75.0% |
| status | 79.2% | 83.3% | 91.7% | 100.0% | 100.0% |
| trace_number | 66.7% | 91.7% | 75.0% | 95.8% | 95.8% |
| response_codes | 83.3% | 83.3% | 83.3% | 100.0% | 100.0% |
| supplier | 83.3% | 83.3% | 79.2% | 100.0% | 100.0% |
| invoice_number | 66.7% | 100.0% | 83.3% | 91.7% | 91.7% |
| invoice_date | 62.5% | 87.5% | 87.5% | 100.0% | 100.0% |
| account_number | 83.3% | 87.5% | 83.3% | 100.0% | 100.0% |
| po_number | 70.8% | 95.8% | 70.8% | 79.2% | 79.2% |
| subtotal | 50.0% | 58.3% | 66.7% | 91.7% | 91.7% |
| hst | 58.3% | 70.8% | 70.8% | 91.7% | 91.7% |
| total | 58.3% | 75.0% | 75.0% | 87.5% | 87.5% |
| qty_ordered | 30.3% | 40.0% | 4.3% | 98.6% | 98.6% |
| qty_shipped | 30.3% | 40.0% | 53.3% | 97.9% | 97.9% |
| unit_cost | 30.3% | 40.0% | 52.9% | 95.9% | 95.9% |
| line_total | 29.0% | 37.9% | 52.9% | 98.6% | 98.6% |
| patient_dob | 37.8% | 48.6% | 56.8% | 89.2% | 89.2% |
| health_card | 58.6% | 75.9% | 62.1% | 82.8% | 82.8% |
| date_written | 52.1% | 66.7% | 64.6% | 87.5% | 87.5% |
| prescriber_name | 68.8% | 75.0% | 68.8% | 85.4% | 85.4% |
| prescriber_license | 60.4% | 79.2% | 68.8% | 62.5% | 62.5% |
| sig | 46.9% | 71.6% | 72.3% | 90.1% | 90.1% |
| refills | 53.1% | 72.8% | 85.2% | 98.8% | 98.8% |

## Error categories

| Pipeline | numeric_mismatch | missing | near_miss | date_mismatch | wrong_value | hallucinated |
|---|---|---|---|---|---|---|
| `ocr_regex` | 41 | 870 | 26 | 2 | 20 | 2 |
| `ocr_reference` | 28 | 601 | 21 | 0 | 18 | 0 |
| `ocr_text_llm` | 236 | 371 | 37 | 12 | 30 | 65 |
| `vision_llm` | 91 | 30 | 24 | 6 | 8 | 0 |
| `vision_verified` | 91 | 30 | 24 | 6 | 8 | 0 |

## Example errors (critical fields, not flagged)

| Pipeline | Doc | Degradation | Field | Truth | Extracted |
|---|---|---|---|---|---|
| `ocr_regex` | claim_005 | fax | din | `03048596` | `93046596` |
| `ocr_regex` | claim_005 | fax | amount_paid | `61.42` | `41.42` |
| `ocr_regex` | claim_011 | fax | din | `02576795` | `O2576795` |
| `ocr_regex` | claim_023 | fax | din | `04294817` | `O4294817` |
| `ocr_regex` | claim_023 | fax | patient_pays | `33.51` | `34.41` |
| `ocr_reference` | claim_004 | noise | response_codes | `D4,D7` | `D4` |
| `ocr_reference` | rx_pad_001 | clean | med1.sig | `1-2 tabs PO Q4-6H PRN pain` | `1-2. tab PO Q4-6H PRN pain` |
| `ocr_reference` | rx_pad_002 | skew | med1.sig | `1-2 tabs PO Q4-6H PRN pain` | `-2 tabs PO Q4-6H PRN pain` |
| `ocr_reference` | rx_pad_006 | low_res | med1.quantity | `100` | `00` |
| `ocr_reference` | rx_pad_009 | blur | med1.quantity | `100` | `00` |
| `ocr_text_llm` | claim_005 | fax | din | `03048596` | `93046596` |
| `ocr_text_llm` | claim_005 | fax | strength | `850 mg` | `50MG` |
| `ocr_text_llm` | claim_005 | fax | amount_paid | `61.42` | `41.42` |
| `ocr_text_llm` | claim_010 | noise | amount_paid | `138.83` | `38783` |
| `ocr_text_llm` | claim_011 | fax | din | `02576795` | `O2576795` |
| `vision_llm` | claim_002 | skew | amount_paid | `0.00` | `169.27` |
| `vision_llm` | claim_002 | skew | patient_pays | `169.27` | `0.00` |
| `vision_llm` | claim_005 | fax | din | `03048596` | `03048595` |
| `vision_llm` | claim_005 | fax | drug_name | `Glucophage` | `GLICOPHAGE` |
| `vision_llm` | claim_005 | fax | patient_pays | `6.83` | `6.93` |
| `vision_verified` | claim_017 | fax | quantity | `60` | `30` |
| `vision_verified` | inv_005 | fax | line1.unit_cost | `214.51` | `21.51` |
| `vision_verified` | inv_017 | fax | line4.unit_cost | `86.72` | `96.72` |
| `vision_verified` | rx_emr_010 | noise | med1.sig | `Take 1 to 2 tablets by mouth every 4 to 6 hours as needed for pain` | `Take 1 to 2 tablets by mouth every 4 to 6 hours as needed, for pain` |
| `vision_verified` | rx_pad_007 | clean | med1.sig | `1-2 caps PO Q4-6H PRN pain` | `Sig: 12 caps PO Q4-6H PRN pain` |
