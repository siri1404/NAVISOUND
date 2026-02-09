from dataclasses import dataclass
from datetime import datetime
import csv
import os

@dataclass
class TestingMetrics:
    participant_id: str
    age_range: str
    vision_status: str

    task_1_completion: bool
    task_1_time_sec: float
    task_1_collisions: int

    task_2_completion: bool
    task_2_time_sec: float
    task_2_collisions: int

    sus_score: int  # System Usability Scale (0-100)
    nps_score: int  # 0-10
    confidence_before: int  # 1-10
    confidence_after: int  # 1-10

    qualitative_feedback: str
    testing_date: str = None

    def __post_init__(self):
        self.testing_date = datetime.now().isoformat()


# Save results to CSV (append)
def save_test_results(metrics: TestingMetrics, out_file: str = 'test_results.csv'):
    file_exists = os.path.exists(out_file)
    with open(out_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(metrics.__dict__.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(metrics.__dict__)


# Analysis
def calculate_metrics_summary(results_file: str = 'test_results.csv'):
    try:
        import pandas as pd
    except Exception:
        print('pandas is required for analysis. Install with `pip install pandas`.')
        return None

    df = pd.read_csv(results_file)

    summary = {
        'n_participants': len(df),
        'avg_task1_time': df['task_1_time_sec'].mean(),
        'avg_task2_time': df['task_2_time_sec'].mean(),
        'avg_sus_score': df['sus_score'].mean(),
        'avg_nps_score': df['nps_score'].mean(),
        'completion_rate': (df['task_1_completion'].sum() / len(df)) * 100,
        'confidence_improvement': (df['confidence_after'] - df['confidence_before']).mean()
    }

    print(f"""
    TESTING RESULTS SUMMARY
    ========================
    Participants: {summary['n_participants']}
    Task Completion: {summary['completion_rate']:.1f}%
    Avg SUS Score: {summary['avg_sus_score']:.1f}/100
    Avg NPS Score: {summary['avg_nps_score']:.1f}/10
    Confidence Improvement: +{summary['confidence_improvement']:.1f} points
    """)

    return summary


if __name__ == '__main__':
    # Simple smoke test: create a sample row when run directly
    sample = TestingMetrics(
        participant_id='sample-001',
        age_range='25-34',
        vision_status='low-vision',
        task_1_completion=True,
        task_1_time_sec=45.0,
        task_1_collisions=0,
        task_2_completion=True,
        task_2_time_sec=60.0,
        task_2_collisions=1,
        sus_score=78,
        nps_score=8,
        confidence_before=4,
        confidence_after=7,
        qualitative_feedback='Helpful but directions sometimes vague.'
    )
    save_test_results(sample)
    print('Wrote sample test row to test_results.csv')

