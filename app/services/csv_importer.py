"""
CSV インポーター
既存の uploadHandler.js の parseNewFormatCSV をPython化
"""

from typing import List, Dict, Tuple
from datetime import date
import csv
import io
from sqlalchemy.orm import Session
from app.models.student import Student
from app.models.grade import Grade
from app.models.class_ import Class


def parse_csv_line(line: str) -> List[str]:
    """CSV の1行を解析（引用符対応）"""
    reader = csv.reader(io.StringIO(line))
    return next(reader)


def parse_new_format_csv(csv_text: str) -> Tuple[List[Dict], List[Dict]]:
    """
    新フォーマットCSVを解析（【生徒データ】【チェックテスト成績】セクション対応）

    Returns:
        (students_list, grades_list) のタプル
    """
    lines = csv_text.strip().split('\n')

    students = []
    grades = []
    current_section = None
    student_header_index = -1
    grade_header_index = -1

    for i, line in enumerate(lines):
        line = line.strip()

        # セクション判別
        if line in ['【生徒データ】セクション', '【生徒データ】']:
            current_section = 'students'
            continue
        elif line in ['【チェックテスト成績】セクション', '【チェックテスト成績】']:
            current_section = 'grades'
            continue
        elif not line:
            continue

        # 生徒データセクション
        if current_section == 'students':
            if ',' in line and student_header_index == -1:
                # ヘッダー行
                student_header_index = i
                continue
            elif student_header_index != -1 and ',' in line:
                # データ行
                try:
                    values = parse_csv_line(line)
                    if len(values) >= 11:
                        student = {
                            'student_code': values[0],
                            'classroom': values[1],
                            'name': values[2],
                            'name_kana': values[3],
                            'gender': values[4],
                            'high_school': values[5],
                            'course_subject': values[6],
                            'school_class': values[7],
                            'club': values[8],
                            'target_university': values[9],
                            'target_dept': values[10]
                        }
                        students.append(student)
                except Exception as e:
                    print(f"Error parsing student row {i}: {e}")
                    continue

        # 成績セクション
        elif current_section == 'grades':
            if ',' in line and grade_header_index == -1:
                # ヘッダー行
                grade_header_index = i
                continue
            elif grade_header_index != -1 and ',' in line:
                # データ行
                try:
                    values = parse_csv_line(line)
                    if len(values) >= 10:
                        grade = {
                            'name': values[0],
                            'lesson_number': int(values[1]) if values[1] else 0,
                            'lesson_content': values[2],
                            'date': values[3],
                            'comprehension': int(values[4]) if values[4] else 0,
                            'unseen_problems': int(values[5]) if values[5] else 0,
                            'grammar': int(values[6]) if values[6] else 0,
                            'vocabulary': int(values[7]) if values[7] else 0,
                            'listening': int(values[8]) if values[8] else 0,
                            'total': int(values[9]) if values[9] else 0
                        }
                        grades.append(grade)
                except Exception as e:
                    print(f"Error parsing grade row {i}: {e}")
                    continue

    if not students:
        raise ValueError('【生徒データ】セクションが見つかるか、データが空です')

    return students, grades


def match_students_to_ids(db: Session, students: List[Dict]) -> List[Tuple[Dict, str]]:
    """
    CSVの生徒データをDBの生徒IDにマッチング

    既存生徒は ID を返し、新規生徒は新しい ID を割り当てる

    Returns:
        [(student_dict, student_id), ...] のリスト
    """
    matched = []

    # 既存の最大 ID を取得
    max_id = 0
    existing_students = db.query(Student).all()
    for s in existing_students:
        try:
            id_num = int(s.id.replace('s', ''))
            if id_num > max_id:
                max_id = id_num
        except (ValueError, AttributeError):
            pass

    for student in students:
        student_name = student['name']

        # 同じ名前の生徒を検索
        existing = db.query(Student).filter(Student.name == student_name).first()

        if existing:
            # 既存生徒: そのIDを使用
            matched.append((student, existing.id))
        else:
            # 新規生徒: 新しいIDを割り当て
            max_id += 1
            new_id = f's{max_id}'
            matched.append((student, new_id))

    return matched


def match_grades_to_students(
    db: Session,
    students_with_ids: List[Tuple[Dict, str]],
    grades: List[Dict]
) -> List[Tuple[Dict, str]]:
    """
    CSV の成績データを生徒IDにマッチング

    Returns:
        [(grade_dict, student_id), ...] のリスト
    """
    # 生徒名 → ID マップを作成
    student_name_to_id = {s[0]['name']: s[1] for s in students_with_ids}

    matched_grades = []
    for grade in grades:
        student_name = grade['name']

        # 生徒名でマッチング
        if student_name in student_name_to_id:
            student_id = student_name_to_id[student_name]
            matched_grades.append((grade, student_id))

    return matched_grades


def save_csv_data(
    db: Session,
    students_with_ids: List[Tuple[Dict, str]],
    matched_grades: List[Tuple[Dict, str]]
) -> Dict:
    """
    CSV データを DB に保存

    Returns:
        {
            "added_students": 追加した生徒数,
            "updated_students": 更新した生徒数,
            "added_grades": 追加した成績数,
            "errors": エラーメッセージのリスト
        }
    """
    results = {
        "added_students": 0,
        "updated_students": 0,
        "added_grades": 0,
        "errors": []
    }

    # 生徒データの保存
    for student, student_id in students_with_ids:
        try:
            existing = db.query(Student).filter(Student.id == student_id).first()

            if existing:
                # 既存生徒を更新
                existing.name = student['name']
                existing.name_kana = student['name_kana']
                existing.classroom = student['classroom']
                existing.gender = student['gender']
                existing.high_school = student['high_school']
                existing.course_subject = student['course_subject']
                existing.school_class = student['school_class']
                existing.club = student['club']
                existing.target_university = student['target_university']
                existing.target_dept = student['target_dept']
                results["updated_students"] += 1
            else:
                # 新規生徒を追加（CSV の student_code から講座を検索）
                student_code = student.get('student_code', '')
                class_obj = db.query(Class).filter(Class.id == student_code).first()
                new_student = Student(
                    id=student_id,
                    name=student['name'],
                    name_kana=student['name_kana'],
                    classroom=student['classroom'],
                    gender=student['gender'],
                    high_school=student['high_school'],
                    course_subject=student['course_subject'],
                    school_class=student['school_class'],
                    club=student['club'],
                    target_university=student['target_university'],
                    target_dept=student['target_dept'],
                    class_id=class_obj.id if class_obj else None,
                    join_date=date.today()
                )
                db.add(new_student)
                results["added_students"] += 1

        except Exception as e:
            results["errors"].append(f"生徒 {student['name']} の保存に失敗: {str(e)}")

    db.commit()

    # 成績データの保存
    for grade, student_id in matched_grades:
        try:
            # 既存の成績をチェック
            existing_grade = db.query(Grade).filter(
                Grade.student_id == student_id,
                Grade.date == grade['date'],
                Grade.lesson_number == grade['lesson_number']
            ).first()

            if existing_grade:
                # 既存成績を更新
                existing_grade.score_comprehension = grade['comprehension']
                existing_grade.score_unseen = grade['unseen_problems']
                existing_grade.score_grammar = grade['grammar']
                existing_grade.score_vocabulary = grade['vocabulary']
                existing_grade.score_listening = grade['listening']
                existing_grade.score_total = grade['total']
            else:
                # 新規成績を追加（生徒の所属講座を使用）
                student_obj = db.query(Student).filter(Student.id == student_id).first()
                new_grade = Grade(
                    id=f"g_{student_id}_{grade['date']}_{grade['lesson_number']}",
                    student_id=student_id,
                    class_id=student_obj.class_id if student_obj else None,
                    date=grade['date'],
                    lesson_number=grade['lesson_number'],
                    lesson_content=grade['lesson_content'],
                    score_comprehension=grade['comprehension'],
                    score_unseen=grade['unseen_problems'],
                    score_grammar=grade['grammar'],
                    score_vocabulary=grade['vocabulary'],
                    score_listening=grade['listening'],
                    score_total=grade['total']
                )
                db.add(new_grade)
                results["added_grades"] += 1

        except Exception as e:
            results["errors"].append(f"成績 {grade['name']} のインポートに失敗: {str(e)}")

    db.commit()

    return results
